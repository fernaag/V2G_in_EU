# Vehicle-to-grid potential and competition to second life batteries in Europe

This repository contains the data, processing scripts, and model used to investigate the competition between vehicle to grid, second life batteries and new stationary storage. The structure of the repo is as follows:

Folder data: This folder contains all data and scripts used to prepare the model. It contains three subfolders:
1. raw_data: Where the raw data from the source is documented and made available as-is.
2. data_handling_scripts: Where the different parameters in the models were calibrated and that contain documentation on how the data was prepared, underlying assumptions, and fits for the scenarios.
3. scenario_data: Here you can find the final data used into the model in various formats.

Folder docs: Here one can find different classes needed for the model to operate with the ODYM framework and an additional folder called "Files", where the configuration and calibration files for ODYM are stored. These provide an overview of the model setup and parameters used.

Folder odym contains further modules needed for odym

Folder results contains the model output for all scenario with the most relevant graphs for each combination.

sankey.py provides a locally hosted web-application where one can interactively view the flows throughout the system for all years and scenarios.

scenario_visualizations.py provides an overview of the key figures that can interactively be assessed via a locally hosted web-application

Model.py main file for the model
