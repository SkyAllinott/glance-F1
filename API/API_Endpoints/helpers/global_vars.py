# Global Variables
NEXT_RACE_API_URL = "http://localhost:4463/f1/next_race/"

# Where API outputs don't match nice values
country_correction_map = {
        "New Zealander": "New Zealand",
        "Italian": "Italy",
        "Argentine": "Argentina"
    }

# For caching, the default polling time is 1 hour
default_expire = 3600