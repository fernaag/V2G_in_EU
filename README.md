# Norwegian model

This repo contains a dynamic stock driven model of the Norwegian vehicle fleet in several layers. The resources are organised as follows: 

1) data_handling -> fitting_and_preparation folders contain several .ipynb scripts which take the raw data, process it into scenaerios, and creates ODYM-ready arrays with the corresponding aspects and sizes. The raw data is not included here due to size limitations on GitHub. 
2) docs->files contains the ODYM configuration and classification files. All parameters are defined manually and not using ODYM excel files. They can be seen at the start of the python script.
3) results->XX shows the plots generated for each scenario 
4) Vehicle_fleet.py is the main script that runs the dynamic stock model based on the parameters. 
