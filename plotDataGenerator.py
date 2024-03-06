import pandas as pd
def plotDataGenerator(start,end,plot_time_freq,price_time_freq):
    time_series = pd.date_range(start=start, end=end, freq=plot_time_freq)
    price_time_series = pd.date_range(start=start, end=end, freq=price_time_freq)
    data=data = range(1, len(time_series) + 1)
    time_series_df = pd.DataFrame(data, index=time_series, columns=['Index'])

    return time_series