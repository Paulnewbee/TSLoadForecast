# %%
from geopy.geocoders import Nominatim
from everything_data.pull_weather_data import get_weather_data
from everything_data.config import get_unique_counties_list
from importlib import reload

# %%

lon_list = []
lat_list = []
geolocator = Nominatim(user_agent="county_lookup")

counties_list = get_unique_counties_list()
lon_lat_county_dict = {}
for county in counties_list:
    county = county + " County, Texas, USA"
    location = geolocator.geocode(county)
    location.latitude, location.longitude
    lon_list.append(location.longitude)
    lat_list.append(location.latitude)
    lon_lat_county_dict[(location.latitude, location.longitude)] = county

# %%
from everything_data import pull_weather_data
from importlib import reload

reload(pull_weather_data)

start_date = "2021-01-01"
end_date = "2026-05-31"


data_list = []
step = 5
for i in range(0, len(lat_list), step):
    lat_subset = lat_list[i : i + step]
    lon_subset = lon_list[i : i + step]
    weather_data_dict = pull_weather_data.get_weather_data(
        lat_subset, lon_subset, start_date, end_date
    )
    # replace lat and lon with county name for weather_data_dict

    sub_counties_list = counties_list[i : i + step]
    for k, value in enumerate(weather_data_dict.values()):
        value.to_pickle(f"TX_{sub_counties_list[k]}_weather_data.pkl")


# %%
