import os, json, inspect, requests
from typing import List, Dict, Optional, Union, Literal, Callable
from pydantic import BaseModel

class ToolCallFunction(BaseModel):
    name: str
    arguments: str
    class Config: exclude_none = True

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction
    class Config: exclude_none = True

class MultiModalContent(BaseModel):
    type: Literal["text", "image_url"]
    text: Optional[str] = None
    image_url: Optional[dict] = None
    class Config: exclude_none = True

class Message(BaseModel):
    role: Literal["system","user","assistant","tool"]
    content: Optional[Union[str,List[MultiModalContent]]] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    class Config: exclude_none = True

class ToolFunction(BaseModel):
    name: str
    description: Optional[str]
    parameters: Dict
    class Config: exclude_none = True

class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunction
    class Config: exclude_none = True

class ChatPayload(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 1.0
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, dict]] = None
    stream: Optional[bool] = None
    class Config: exclude_none = True


class NominaLlm:
    def __init__(self, api_key=None, site_url="", site_name="", default_model="openrouter/optimus-alpha"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.site_url = site_url
        self.site_name = site_name
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.models_url = "https://openrouter.ai/api/v1/models"
        #self.models_url = "http://ailab.local:8181/v1/models"
        #self.base_url = "http://ailab.local:8181/v1/chat/completions"
        self.default_model = default_model
        self.tools: List[Tool] = []
        self.tool_funcs: Dict[str, Callable] = {}

    def add_tool(self, func: Callable):
        name, desc = func.__name__, func.__doc__ or ""
        sig, props, required = inspect.signature(func), {}, []
        for pname, param in sig.parameters.items():
            props[pname] = {"type": "string", "description": ""}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        parameters = {"type": "object", "properties": props, "required": required}
        tool = Tool(function=ToolFunction(name=name, description=desc, parameters=parameters))
        self.tools.append(tool)
        self.tool_funcs[name] = func

    def _build_headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.site_url: headers["HTTP-Referer"] = self.site_url
        if self.site_name: headers["X-Title"] = self.site_name
        return headers

    def make_text_message(self, role:str, content:str) -> Message:
        return Message(role=role, content=content)

    def chat(self, messages: List[Message], temperature=1.0, model=None):
        conversation = list(messages)

        while True:
            payload = ChatPayload(
                model=model or self.default_model,
                messages=conversation,
                temperature=temperature,
                tools=self.tools if self.tools else None,
                tool_choice="auto" if self.tools else None
            )
            resp = requests.post(self.base_url, headers=self._build_headers(),
                                 json=payload.model_dump(exclude_none=True))
            resp.raise_for_status()
            response_json = resp.json()
            msg = response_json["choices"][0]["message"]
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                conversation.append(msg)

                for call in tool_calls:
                    fn = call["function"]["name"]
                    args = json.loads(call["function"]["arguments"])
                    try:
                        result = self.tool_funcs[fn](**args)
                    except Exception as e:
                        result = f"Error calling `{fn}`: {e}"

                    conversation.append(Message(
                        role="tool",
                        content=str(result),
                        tool_call_id=call["id"]
                    ))
            else:
                return response_json

    def list_models(self) -> List[Dict[str, str]]:
        """Fetch list of available OpenRouter models"""
        response = requests.get(self.models_url, headers=self._build_headers())
        response.raise_for_status()
        data = response.json()
        models = []
        for m in data.get("data", []):
            model_id = m.get("id")
            model_name = m.get("name") or model_id
            models.append({"id": model_id, "name": model_name})
        return models
