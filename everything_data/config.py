load_zone_county_mapping = {
    "ERCOT": {
        "North": {
            "Core1": ["Dallas", "Collin", "Denton"],
            "Core2": ["Fort Worth", "Tarrant", "Ellis"],
            "Core3": ["Smith"],
            # "North":["Grayson","Fannin","Lamar","Cooke"], "South":["Grimes","Btsxod","Robertson"],
            # "East":["Rusk","Nacogdoches","Angelina","Smith","Cherokee"],
            # "West":["Jask","Young","Stephens","Eastland","Comanche"]
        },
        "South": {
            "Core1": ["Austin", "Washington", "Waller"],
            "Core2": ["Bexar"],
            "Core3": ["Hidalgo"],
            "Core4": ["San Patricio"],
            # "North":["Bell","Lampasa","San Saba"],
            # "South":["Cameron","Hidalgo","Starr","Willacy"],
            # "West": ["Kinney","Edwards","Kimble","Mason"]
            # "East": [""]
        },
        "West": {
            "Core1": ["Wichita"],
            "Core2": ["Midland"],
            "Core3": ["Lubbock"],
            "Core4": ["Taylor"],
        },
        "Houston": {"Core1": ["Harris", "Fort Bend", "Montgomery"]},
    }
}

weather_zone_county_mapping = {
    "ERCOT": {
        "North": {"Core1": ["Wichita"], "Core2": ["Lubbock"]},
        "Far West": {
            "Core1": ["Midland"],
        },
        "West": {"Core1": ["Taylor"]},
        "South": {"Core1": ["Hidalgo"], "Core2": ["San Patricio"]},
        "Coast": {"Core1": ["Harris", "Fort Bend", "Montgomery"]},
        "South Central": {
            "Core1": ["Austin", "Washington", "Waller"],
            "Core2": ["Bexar"],
        },
        "North Central": {
            "Core1": ["Dallas", "Collin", "Denton"],
            "Core2": ["Fort Worth", "Tarrant", "Ellis"],
        },
        "East": {"Core1": ["Smith"]},
        "North": {"Core1": ["Wichita"], "Core2": ["Lubbock"]},
    }
}

ERCOT_LOAD_DATA_ADDRESS_LIST = [
    "https://www.ercot.com/files/docs/2025/02/11/Native_Load_2025.zip",
    "https://www.ercot.com/files/docs/2024/02/06/Native_Load_2024.zip",
    "https://www.ercot.com/files/docs/2023/02/09/Native_Load_2023.zip",
    "https://www.ercot.com/files/docs/2022/02/08/Native_Load_2022.zip",
    "https://www.ercot.com/files/docs/2021/11/12/Native_Load_2021.zip",
    "https://www.ercot.com/files/docs/2021/01/12/Native_Load_2020.zip",
    "https://www.ercot.com/files/docs/2020/01/09/Native_Load_2019.zip",
]

ERCOT_PRICE_DATA_ADDRESS_LIST = [
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=1140421628",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=1065468714",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=969803138",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=886627599",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=814918746",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=751351545",
    "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=694281912",
]


def get_unique_counties(mapping_type="both"):
    """
    Extract unique county names from weather_zone_county_mapping or load_zone_county_mapping.

    Args:
        mapping_type (str): "weather", "load", or "both" to specify which mapping(s) to use

    Returns:
        set: A set of unique county names
    """
    unique_counties = set()

    if mapping_type in ["weather", "both"]:
        for region, cores in weather_zone_county_mapping["ERCOT"].items():
            for core, counties in cores.items():
                unique_counties.update(counties)

    if mapping_type in ["load", "both"]:
        for region, cores in load_zone_county_mapping["ERCOT"].items():
            for core, counties in cores.items():
                unique_counties.update(counties)

    return unique_counties


def get_unique_counties_list(mapping_type="both"):
    """
    Extract unique county names from weather_zone_county_mapping or load_zone_county_mapping.

    Args:
        mapping_type (str): "weather", "load", or "both" to specify which mapping(s) to use

    Returns:
        list: A sorted list of unique county names
    """
    unique_counties = get_unique_counties(mapping_type)
    return sorted(list(unique_counties))
