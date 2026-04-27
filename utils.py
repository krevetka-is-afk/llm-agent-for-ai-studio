def _extract_text(event) -> str | None:
    """Extract text from ThreadStreamEvent"""
    try:
        if event.type == "thread.item.updated":
            data = event.update

            if hasattr(data, "delta"):
                return data.delta

            if hasattr(data, "text"):
                return data.text
    except Exception as e:
        print(e)
    return None
