
#%%
from geopy.geocoders import Nominatim
from everything_data.pull_weather_data import get_weather_data
from everything_data.config import get_unique_counties_list
from importlib import reload

#%%

lon_list = []
lat_list = []
geolocator = Nominatim(user_agent="county_lookup")

conties_list = get_unique_counties_list()
for county in conties_list:
      county = county + " County, Texas, USA"
      location = geolocator.geocode(county)
      location.latitude, location.longitude
      lon_list.append(location.longitude)
      lat_list.append(location.latitude)

#%%
start_date = "2015-01-01"
end_date = "2025-09-30"

weather_data_dict = get_weather_data(lat_list, lon_list, start_date, end_date)

#%%

