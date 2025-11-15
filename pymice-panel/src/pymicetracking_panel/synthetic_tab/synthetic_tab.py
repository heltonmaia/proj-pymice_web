import panel as pn


def get_tab() -> pn.Column:
    return pn.Column(
        pn.pane.Markdown(
            "## Synthetic Data\nSynthetic data generation and tools will appear here."
        ),
        margin=(10, 0),
    )
