import shutil

def render_sotp_tower(segments_ev: list[dict]) -> str:
    """
    segments_ev: list of {'name': str, 'ev': float}
    Returns a terminal string showing a stacked tower using block characters.
    """
    # Fallback to 80 if terminal width detection fails
    width = shutil.get_terminal_size((80, 24)).columns
    terminal_width = width - 2
    max_height = 20   # rows for the tower
    total_ev = sum(item['ev'] for item in segments_ev)

    if total_ev == 0:
        return "No valuation data."

    # Calculate heights (rows) proportional to EV
    heights = []
    for item in segments_ev:
        h = max(1, round((item['ev'] / total_ev) * max_height))
        heights.append(h)

    # Normalize total height to max_height
    total_h = sum(heights)
    if total_h > max_height:
        # scale down proportionally
        factor = max_height / total_h
        heights = [max(1, int(h * factor)) for h in heights]
    # adjust last to fill exactly max_height
    while sum(heights) < max_height:
        heights[-1] += 1
    heights[-1] -= sum(heights) - max_height

    lines = []
    for idx, item in enumerate(segments_ev):
        name = item['name'][:10]   # truncate
        block = '█' * (terminal_width - 25)
        for _ in range(heights[idx]):
            ev_label = f"${item['ev']:,.0f}"
            line = f"{name:10s} {ev_label:>12s} {block}"
            lines.append(line)

    # Print from top to bottom (reverse order to stack bottom-up)
    lines.reverse()
    return '\n'.join(lines)
