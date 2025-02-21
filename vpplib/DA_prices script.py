# -*- coding: utf-8 -*-
"""
Created on Thu Nov 16 12:23:24 2023

@author: smkibors


This script is for fteching the Day ahead market prices from the ENTSO-e data transparency platform 
An API key is needed to access the data from the platform. First an account should be created for the platform https://transparency.entsoe.eu/dashboard/show 
and then the key can be requested by sending an email to transparency@entsoe.eu 

"""
import entsoe
import pandas as pd
import matplotlib.pyplot as plt

client = entsoe.EntsoePandasClient(api_key= '9ebdb4aa-d21a-414f-83f4-d4027a6a70b9')  #The key can be requested on the Entsoe data transparency platform 
start = pd.Timestamp('202301010000', tz='Europe/Berlin') #format of the timestamp 'YYYYMMDDHHmm'
end = pd.Timestamp('202310010000', tz='Europe/Berlin') 
cl = 'DE_LU'
Day_ahead_prices = client.query_day_ahead_prices(country_code=cl, start=start, end=end)
Day_ahead_prices_Numpy=Day_ahead_prices.to_numpy()
Day_ahead_prices_pd_1h=pd.DataFrame(Day_ahead_prices_Numpy, columns = ['Day-Ahead Prices'])

csv_file = 'Day_ahead_prices.csv'
Day_ahead_prices_pd_1h.to_csv(csv_file)

print(Day_ahead_prices)

plt.figure(figsize=(12, 6))
plt.plot(Day_ahead_prices_pd_1h.index, Day_ahead_prices_pd_1h['Day-Ahead Prices'], label='Day-Ahead Prices')
plt.title('Day-Ahead Electricity Prices')
plt.xlabel('Date')
plt.ylabel('Price (EUR/MWh)')
plt.legend()
plt.grid(True)
plt.show()