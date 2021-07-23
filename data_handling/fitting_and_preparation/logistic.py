# Logistic fit
import numpy as np
def logistic(x,ti,tau,C0,C1):
    """
    ti: inflection time
    tau: transition time coefficient
    C0: start value
    C1: end value
    x: vector of observation points (time)
    """

    return (C1 - C0)/(1 + np.exp(-(x - ti) / tau)) + C0  