"""URL converters shared across check routes."""


class TechnologyConverter:
    regex = "2G|3G|4G|5G"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return str(value)
