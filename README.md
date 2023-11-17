# Vehicle-to-grid potential and competition to second life batteries in Europe

This repository contains the data, processing scripts, and model used to investigate the competition between vehicle to grid, second life batteries and new stationary storage. The structure of the repo is as follows:

Folder data: This folder contains all data and scripts used to prepare the model. It contains three subfolders:
1. raw_data: Where the raw data from the source is documented and made available as-is.
2. data_handling_scripts: Where the different parameters in the models were calibrated and that contain documentation on how the data was prepared, underlying assumptions, and fits for the scenarios.
3. scenario_data: Here you can find the final data used into the model in various formats.

Folder docs: Here one can find different classes needed for the model to operate with the ODYM framework and an additional folder called "Files", where the configuration and calibration files for ODYM are stored. These provide an overview of the model setup and parameters used.

Folder odym contains further modules needed for odym

Folder results contains the model output for all scenario with the most relevant graphs for each combination.

Model.py main file for the model used to generate the non-constrained model related to Figure 1 in the manuscript. 

Model_constrained.py is the main file for the model on the competition of V2G, SLBs, and NSBs in a limited energy market related to all other figures in the manuscript. 

The Requirements.txt files specify the packages needed to run this code. 

Demo: Once the requirements are installed and the file paths accordingly adjusted, you should be able to successfully run the code. Running the Model.py and Model_constrained.py files should compute all the scenario values for all the variables. Executing the corresponding plot functions specified at the end of the files should generate the relevant figures. Doing so without altering the underlying data should fully reproduce the results presented in the manuscript. 
