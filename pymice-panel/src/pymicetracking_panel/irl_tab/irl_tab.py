import panel as pn


def get_tab() -> pn.Column:
    return pn.Column(
        pn.pane.Markdown("## IRL Analysis\nIRL analysis tools will appear here."),
        margin=(10, 0),
    )
