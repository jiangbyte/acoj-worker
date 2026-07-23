"""输出比对：简化字符串比对，忽略末尾空白差异。"""


def check_output(actual_preview: str, expected_text: str | None) -> bool:
    """比对实际输出和预期输出，返回是否匹配。None 预期视为全匹配。"""
    if expected_text is None:
        return True
    return actual_preview.strip() == expected_text.strip()
