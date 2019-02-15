from pysisyphus.calculators.AnaPotBase import AnaPotBase

# See J. Chem. Phys. 122 174106 (2005)
# https://doi.org/10.1063/1.1885467
# Eq. (11)

class FourWellAnaPot(AnaPotBase):

    def __init__(self): 
        V_str = "x**4 + y**4 - 2*x**2 - 4*y**2 + x*y + 0.3*x + 0.1*y"
        xlim = (-1.75, 1.75)
        ylim = (-1.75, 1.75)
        super().__init__(V_str=V_str, xlim=xlim, ylim=ylim)

    def __str__(self):
        return "FourWellAnaPot calculator"


if __name__ == "__main__":
    fw = FourWellAnaPot()
    fw.plot()
    import matplotlib.pyplot as plt
    plt.show()
