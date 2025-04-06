from textual.widgets import Tabs as TextualTabs
from textual import events

class TabsWithClose(TextualTabs):
    def get_tab_at(self, x, y):
        for tab in self.children:
            region = getattr(tab, 'region', None)
            if region is None:
                region = getattr(tab, 'bounding_region', None)
            if region and region.contains(x, y):
                return tab
        return None

    def on_mouse_down(self, event: events.MouseDown):
        tab_clicked = self.get_tab_at(event.x, event.y)
        if tab_clicked:
            if getattr(event, 'num_presses', 1) == 2:
                self.remove_tab(tab_clicked.id)
            else:
                self.active = tab_clicked.id
        event.stop()
