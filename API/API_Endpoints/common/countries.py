import pycountry


COUNTRY_REPLACEMENTS = {
    "Great Britain": "GB",
    "United States": "US",
    "New Zealander": "New Zealand",
    "Italian": "Italy",
    "Argentine": "Argentina",
}


def normalize_country(country_name: str) -> str:
    return COUNTRY_REPLACEMENTS.get(country_name, country_name)


def country_to_code(country_name: str) -> str:
    try:
        country_name = normalize_country(country_name)
        return pycountry.countries.lookup(country_name).alpha_2.lower()
    except Exception:
        return ""
