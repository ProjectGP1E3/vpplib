#from hamcrest import none
from matplotlib import style
from matplotlib.lines import drawStyles, lineStyles
from torch import t
from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.electrical_energy_storage import ElectricalEnergyStorage
from vpplib.photovoltaic import Photovoltaic

from vpplib.heat_pump import HeatPump
from plotDataGenerator import *
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB

class PvBessOptimization():
    def __init__(self):
        self.intialize_pvbess_parameters()
    
    def intialize_pvbess_parameters(self):

        # Battery Variables Initialization
        self.maxChargingPower=1 #KW/h
        self.maxDischargingPower=0.9#KW/h
        self.dischargingEfficiency=0.9
        self.chargingEfficiency=0.9
        self.minimumSoC=20
        self.maximumSoC=90
        self.startSoC=45
        self.max_power = 1 # kW
        self.capacity = 100  # kWh
        self.max_c = 1

        # Values for environment
        self.start = "2015-05-01 00:00:00"
        self.end = "2015-05-10 23:45:00"
        self.number_of_days=10
        self.year = "2015"
        self.time_freq = "15 min"
        self.timebase = 15
        self.time_series = pd.date_range(start=self.start, end=self.end, freq=self.time_freq)
        self.price_time_series = pd.date_range(start=self.start, end=self.end, freq="60 min")
        data=data = range(1, len(self.time_series) + 1)
        self.df = pd.DataFrame(data, index=self.time_series, columns=['Index'])
        # Environment initialization
        self.environment = Environment(
            timebase=self.timebase,
            start=self.start,
            end=self.end,
            year=self.year,
            time_freq=self.time_freq,
        )


        # Values for user_profile
        self.latitude = 50.941357
        self.longitude = 6.958307
        self.building_type = "DE_HEF33"
        self.t_0 = 40

        #User profile Initialization
        self.user_profile = UserProfile(
            identifier=None,
            latitude=self.latitude,
            longitude=self.longitude,
            building_type=self.building_type,
            comfort_factor=None,
            t_0=self.t_0,
        )
        

        # PV
        unit = "kW"
        name = "PVbus"
        module_lib = "SandiaMod"
        module = "Canadian_Solar_CS5P_220M___2009_"
        inverter_lib = "cecinverter"
        inverter = "Connect_Renewable_Energy__CE_4000__240V_"
        surface_tilt = 20
        surface_azimuth = 200
        modules_per_string = 7
        strings_per_inverter = 3
        temp_lib = 'sapm'
        temp_model = 'open_rack_glass_glass'

        pv = Photovoltaic(
            unit=unit,
            identifier=(name + "_pv"),
            environment=self.environment,
            user_profile=self.user_profile,
            module_lib=module_lib,
            module=module,
            inverter_lib=inverter_lib,
            inverter=inverter,
            surface_tilt=surface_tilt,
            surface_azimuth=surface_azimuth,
            modules_per_string=modules_per_string,
            strings_per_inverter=strings_per_inverter,
            temp_lib=temp_lib,
            temp_model=temp_model
        )
         # creating an ESS
        ESS = ElectricalEnergyStorage(
            unit=unit,
            identifier=(name + "_storage"),
            environment=self.environment,
            user_profile=self.user_profile,
            capacity=self.capacity,
            charge_efficiency=self.chargingEfficiency,
            discharge_efficiency=self.dischargingEfficiency,
            max_power=self.max_power,
            max_c=self.max_c,
        )

        
        self.environment.get_pv_data(file="./input/pv/dwd_pv_data_2015.csv")
        pv.prepare_time_series()
        self.pvPower=pv.timeseries.loc[self.start:self.end]

        baseload = pd.read_csv("./input/baseload/df_S_15min.csv")
        baseload.drop(columns=["Time"], inplace=True)
        baseload.set_index(self.environment.pv_data.index, inplace=True)

        # combine baseload and pv timeseries to get residual load
        house_loadshape = pd.DataFrame(baseload["0"].loc[self.start:self.end] / 1000)
        house_loadshape["pv_gen"] = self.pvPower.loc[self.start:self.end]
        house_loadshape["Excess_Power"] = ( self.pvPower.PVbus_pv-(baseload["0"].loc[self.start:self.end] / 1000) )#type :ignore
        self.ExcessPower=house_loadshape.Excess_Power
        house_loadshape["baseload"]=(baseload["0"].loc[self.start:self.end]/1000)

        self.pvPowerGenerated=house_loadshape.pv_gen
        self.baseloadData=house_loadshape.baseload
        
        self.pvPower_use=self.ExcessPower # type: ignore
        self.systemLoad=-1*self.pvPower_use
        self.systemLoad[self.systemLoad<0]=0
        self.outputLoad=1*self.systemLoad
        self.outputLoad[self.outputLoad>self.maxDischargingPower]=self.maxDischargingPower
        self.pvPower_use[self.pvPower_use<0]=0

     
        self.prices = self.environment.get_price_data()

    def pvbess_model(self):
        time_step_size = 15
        number_of_days = 10
        num_hours=number_of_days*24
        num_time_step=int(num_hours*60//time_step_size)
        T = num_time_step
        set_T = range(0,T)
        timestep=15
        timestepHour=60//timestep

       
        
        # Create models
        m = gp.Model('MIP')
        m.setParam('TimeLimit',5*60)


        prices_use=self.prices.iloc[40:T+40, 0].values
        

        priceModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}
        pvPowerModel= {t: self.pvPower_use[(t *time_step_size)//60] for t in set_T}
        loadModel= {t: self.outputLoad[(t *time_step_size)//60] for t in set_T}
        systemLoadModel={t: self.systemLoad[(t *time_step_size)//60] for t in set_T}
        chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=self.maxChargingPower,name="chargingPower_{}".format(t)) for t in set_T}
        dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=self.maxDischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}
        chargingState = {t:m.addVar(vtype=GRB.INTEGER,lb=0,ub=1,name="chargingState_{}".format(t)) for t in set_T}
        dischargingState = {t:m.addVar(vtype=GRB.INTEGER ,lb=0,ub=1,name="dischargingState_{}".format(t)) for t in set_T}
        SoC={t:m.addVar(vtype=GRB.CONTINUOUS,lb=self.minimumSoC,ub=self.maximumSoC ,name="chargePercentage_{}".format(t)) for t in set_T}

        ##Constraints on charging process
        #chargingPower constraints
        constraints_eq1={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= chargingState[t] * self.maxChargingPower ,name='chargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore 
        #state of charge constraint
        constraints_eq2={t: m.addConstr(lhs = SoC[t-1] + self.chargingEfficiency*timestepHour*chargingPower[t],sense = GRB.LESS_EQUAL,rhs= self.maximumSoC,name='chargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
        constraints_eq7={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= pvPowerModel[t] ,name='chargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
        # Constraints on discharging process
        #chargingPower constraints
        constraints_eq3={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= dischargingState[t] * self.maxDischargingPower ,name='dischargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore
        #constraints_eq8={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= dischargingState[t] *loadModel[t] ,name='dischargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
        #state of charge constraint
        constraints_eq4={t: m.addConstr(lhs = SoC[t-1] - (1/self.dischargingEfficiency)*timestepHour*dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= self.minimumSoC ,name='dischargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore

        #Constraints on Processes
        constraints_eq5={t: m.addConstr(lhs = chargingState[t]+dischargingState[t],sense = GRB.LESS_EQUAL,rhs= 1 ,name='chargingDischargingCorrelation_constraint_{}'.format(t)) for t in set_T} # type: ignore

        #Constraints on Charge
        constraints_eq6=   {t: m.addConstr(lhs=SoC[t] ,sense = GRB.EQUAL,rhs= SoC[t-1]+self.chargingEfficiency*timestepHour*chargingPower[t]-timestepHour*(1/self.dischargingEfficiency)*dischargingPower[t],name='charge_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
        constraints_eq6[0]=    m.addConstr(lhs=SoC[0] ,sense = GRB.EQUAL,rhs= self.startSoC,name='charge_constraint_{}'.format(0)) # type: ignore

        objective = gp.quicksum(-( chargingPower[t] * timestepHour * priceModel[t])+ (dischargingPower[t]* timestepHour *priceModel[t]) - (systemLoadModel[t]* timestepHour *priceModel[t]) + (pvPowerModel[t] * timestepHour * priceModel[t]) for t in set_T) # type: ignore

        m.ModelSense = GRB.MAXIMIZE
        m.setObjective(objective)
        # Solve the optimization problem
        m.optimize()

        # Extracting timeseries
        charging_power_values = [chargingPower[t].X for t in set_T]
        discharging_power_values = [dischargingPower[t].X for t in set_T]
        systemLoad_values=[ systemLoadModel[t] for t in set_T]
        SoC_values = [SoC[t].X for t in range(1, T)]  # Starting from 1 because we don't have charge[0]
        SoC_values.insert(0,self.startSoC)
        time_steps = list(set_T)
        prices_use=self.prices.iloc[40:num_hours+40, 0].values


      
        #load and system
        fig, (ax1, ax2 )= plt.subplots(2, 1, figsize=(10, 15))

        # Plotting residuals
        ax1.plot(self.time_series, list(loadModel.values()), label='Residuals Limited by Discharging Power (kW)', color='b')

        # Plotting system on the same subplot with a dashed line
        ax1.plot(self.time_series,systemLoad_values, label='Residual load (kW)', color='r', linestyle='--')

        # Plotting residuals
        ax2.plot(self.time_series, list(loadModel.values()), label='Residuals (kW)', color='b')
        # Plotting discharging on the same subplot with a dashed line
        ax2.plot(self.time_series,discharging_power_values, label='Discharging Values (kW)', color='g')
        # Setting a general y-label
        ax1.set_ylabel('kW')
        ax1.set_xlabel('Timestamps')
        ax1.set_title('System and Residual load')

        # Adjusting tick parameters
        ax1.tick_params(axis='y')
        ax2.tick_params(axis='y')

        # Add grid and legend
        ax1.grid(True)
        ax1.legend(loc='upper left')
        ax2.grid(True)
        ax2.legend(loc='upper left')

        # Display the plot
        plt.tight_layout()
        plt.show()
        


        #load, soc, pv
        fig, (ax1, ax2, ax3,ax4) = plt.subplots(4, 1, figsize=(10, 15))

        # Plotting PV power model on the first subplot
        ax1.plot(self.time_series, list(loadModel.values()), label='Residuals', color='maroon')
        ax1.set_ylabel('Residuals (kW)', color='maroon')
        ax1.tick_params(axis='y', labelcolor='maroon')
        ax1.legend(loc='upper left')
        #ax1.set_title('PV Power Model')
        ax1.grid(True)  

        # Plotting SOC on the second subplot
        ax2.plot(self.time_series,SoC_values, label='SoC', color='limegreen')
        ax2.set_ylabel('SoC (%)', color='limegreen')
        ax2.tick_params(axis='y', labelcolor='limegreen')
        ax2.legend(loc='upper left')
        #ax2.set_title('State of Charge')
        ax2.grid(True)  

        # Plotting PV on the third subplot
        ax3.plot(self.time_series, list(pvPowerModel.values()), label='PV', color='orange')
        ax3.set_ylabel('PV (kWh)', color='orange')
        #ax3.set_xlabel('Timestamps')
        ax3.tick_params(axis='y', labelcolor='orange')
        ax3.legend(loc='upper left')
        #ax3.set_title('Price')
        ax3.grid(True)

        # Plotting Price on the fourth subplot
        ax4.plot(self.time_series,list(priceModel.values()), label='Price', color='indigo')
        ax4.set_ylabel('Price (€)', color='indigo')
        #ax3.set_xlabel('Timestamps')
        ax4.tick_params(axis='y', labelcolor='indigo')
        ax4.legend(loc='upper left')
        #ax3.set_title('Price')
        ax4.grid(True)



        # Optionally, set a common x-axis label
        #fig.text(0.5, 0.04, 'Time', ha='center')

        plt.suptitle('Battery behaviour w.r.t Residual load, PV and Electricity Prices')

        # Adjust layout for better spacing
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])

        # Display the plot
        plt.show()






        #charging, discharging, SOC
        fig, (ax1,ax2) = plt.subplots(2,1 ,figsize=(12, 6))

        plot_discharging_power_values = [-value for value in discharging_power_values]
        df=pd.DataFrame({'Time':self.time_series,'ChargingPower':charging_power_values,'DischargingPower':plot_discharging_power_values,'SoC':SoC_values})
        # Plotting Charging Power as positive bars
        ax1.bar(df['Time'],df['ChargingPower'], width= 0.05,label='Charging Power (kW)', color='blue')

        # Plotting Discharging Power as negative bars
        ax1.bar(df['Time'],df['DischargingPower'], width= 0.05,label='Discharging Power (kW)', color='orange')

        # Creating a secondary y-axis for the SOC
        #ax2 = ax1.twinx()

        # Plotting the SOC on the secondary y-axis
        ax2.plot(df['Time'],df['SoC'], label='SoC (%)', color='green', linestyle='-')

        # Adding labels, title, and grid
        #ax1.set_xlabel('Timestamps')
        ax1.set_ylabel('Power (kW)', color='blue')
        ax2.set_ylabel('SoC (%)', color='black')
        plt.suptitle('Charging/Discharging Power and SoC over Time')
        ax1.grid(True)
        ax2.grid(True)

        # Adding legends
        ax1.legend(loc='upper left')
        ax2.legend(loc='upper right')

        # Making the y-axis label color match the data
        ax1.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='black')

        plt.show()




        #pv,soc, prices
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15))

        # Plotting PV power model on the first subplot
        ax1.plot(self.time_series,self.pvPowerGenerated, label='PV Generated', color='orange')
        ax1.set_ylabel('PV (kWh)', color='orange')
        ax1.tick_params(axis='y', labelcolor='orange')
        ax1.legend(loc='upper left')
        #ax1.set_title('PV Power Model')
        ax1.grid(True)  # Enable grid

        # Plotting SOC on the second subplot
        ax2.plot(self.time_series,self.baseloadData, label='baseload Data', color='blue')
        ax2.set_ylabel('Baseload (kWh)', color='blue')
        ax2.tick_params(axis='y', labelcolor='blue')
        ax2.legend(loc='upper left')
        #ax2.set_title('State of Charge')
        ax2.grid(True)  

        # Plotting Price on the third subplot
        ax3.plot(self.time_series,self.ExcessPower, label='Excess Power', color='green')
        #ax3.set_ylabel('Power kWh', color='green')
        ax3.plot(self.time_series,-1*self.systemLoad, label='Excess Load', color='red')
        ax3.set_ylabel('kWh', color='black')
        #ax3.set_xlabel('Timestamps')
        ax3.tick_params(axis='y', labelcolor='black')
        ax3.legend(loc='upper left')
        #ax3.set_title('Price')
        ax3.grid(True) 

        # Optionally, set a common x-axis label
        #fig.text(0.5, 0.04, 'Time', ha='center')
        plt.suptitle('Battery behaviour w.r.t PV and Prices')


        # Adjust layout for better spacing
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])

        # Display the plot
        plt.show()



        #load,soc,prices
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15))

        # Plotting PV power model on the first subplot
        ax1.plot(self.time_series, list(loadModel.values()), label='Residual load', color='b')
        ax1.set_ylabel('Residual load (kW)', color='b')
        ax1.tick_params(axis='y', labelcolor='b')
        ax1.legend(loc='upper left')
        #ax1.set_title('PV Power Model')
        ax1.grid(True)  # Enable grid

        # Plotting SOC on the second subplot
        ax2.plot(self.time_series,SoC_values, label='SoC', color='g')
        ax2.set_ylabel('SoC (%)', color='g')
        ax2.tick_params(axis='y', labelcolor='g')
        ax2.legend(loc='upper left')
        #ax2.set_title('State of Charge')
        ax2.grid(True)  

        # Plotting Price on the third subplot
        ax3.plot(self.price_time_series,prices_use, label='Price', color='r')
        ax3.set_ylabel('Price (€)', color='r')
        #ax3.set_xlabel('Timestamps')
        ax3.tick_params(axis='y', labelcolor='r')
        ax3.legend(loc='upper left')
        #ax3.set_title('Price')
        ax3.grid(True)

        # Optionally, set a common x-axis label
        #fig.text(0.5, 0.04, 'Time', ha='center')
        plt.suptitle('Battery behaviour w.r.t Residual load and Prices')


        # Adjust layout for better spacing
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])

        # Display the plot
        plt.show()



if __name__ == "__main__":
    optimization = PvBessOptimization()
    optimization.pvbess_model()