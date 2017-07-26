"""
Provide plotting functions for genomic data types.

Many common data types used in genomics research are supported. Including, but not
limited to, :class:`Hi-C <kaic.plotting.hic_plotter.HicPlot>`,
:class:`bed <kaic.plotting.plotter.GenomicFeaturePlot>`,
:class:`bigwig <kaic.plotting.plotter.BigWigPlot>`
and :class:`gene (GTF) <kaic.plotting.plotter.GenePlot>` file visualization.
The basic idea is that figures can be composed of multiple panels which are
arranged vertically and share a common x-axis representing genomic coordinates.

Each panel is created separately and then combined into a single figure.
For example, when analyzing Hi-C data it is often interesting to correlate
features in the Hi-C map with ChIP-seq tracks. In that case, one would first
create a :class:`~kaic.plotting.hic_plotter.HicPlot` object, which visualizes
Hi-C data, and then a :class:`~kaic.plotting.plotter.BigWigPlot` object, which
can plot bigwig files that are used during ChIP-seq analysis. Finally, the two
objects are used to create a :class:`~kaic.plotting.plotter.GenomicFigure`.

Examples:

Kaic comes with a few example datasets that can be used to explore the basic
functionalities of the plotting module. The paths in this example are relative
to the top-level kaic directory where the setup.py file is located.

.. note::
    The path of the example datasets can be accessed easily using the example_data
    dictionary:

    .. code:: python

        import kaic
        print(kaic.example_data)

.. code:: python

    import kaic.plotting as kplot

    # Create Hic plot
    hplot = kplot.HicPlot("kaic/test/data/test_network/rao2014.chr11_77400000_78600000.hic")

    # Create plot showing some CTCF ChIP-seq data from ENCODE
    bplot = kplot.BigWigPlot("kaic/test/data/test_plotting/CTCF_ChIP_FE_chr11_77-80Mb_mouse_embryo_fibroblasts.bigwig",
                             title="CTCF ChIP", ylabel="fold enrichment")

    # Create plot of all genes in the region. The squash option in combination
    # with the group_by option causes all exons of each gene to be merged.
    # This is useful if the number of alternative transcripts is overwhelming
    # the plot.
    gplot = kplot.GenePlot("kaic/test/data/test_plotting/genes_mm10_chr11_77-80Mb.gtf.gz",
                           group_by="gene_name", squash=True, show_labels=False,
                           title="mm10 genes")

    # The created plots are used to generate a figure by passing them as a list
    # to the GenomicFigure constructor. The order in which they are passed
    # determines the order of panels in the figure.
    gfig = kplot.GenomicFigure([hplot, bplot, gplot])

    # Plot a specific region of the genome
    fig, axes = gfig.plot("chr11:77400000-78600000")

    # Open plot in an interactive window
    fig.show()

.. figure:: ../../../kaic-doc/images/example_plot.png

    Example rendering of the above code saved using
    ``fig.savefig("example.png", dpi=100)``.

The :meth:`GenomicFigure.plot() <kaic.plotting.plotter.GenomicFigure.plot>` function
returns standard matplotlib Figure and a list of Axes instances that can be further
adjusted using standard matplotlib methods. The matplotlib axes instance
associated with each plot is also accesible from the "ax" property of each plot.

.. warning:: The Axes instances of the plot should only be edited after
    :meth:`GenomicFigure.plot() <kaic.plotting.plotter.GenomicFigure.plot>`
    has been called. Otherwise any changes that were made may be overwritten
    when the plot() method is called.

For example, to add a bit of annotating text at a specific location in the
BigWigPlot, the example above can be edited as follows:

.. code:: python

    fig, axes = gfig.plot("chr11:77400000-78600000")
    bplot.ax.text(77850000, 60, "Interesting peak!")
    fig.show()

The coordinates in the Axes are data coordinates, the x-axis is genomic
coordinates on the current chromosome and the y-axis in this case the
fold-enrichment of the bigwig track.

.. note::
    An explanation of each plot class and the parameters that it supports can be
    accessed by suffixing a question mark (in Ipython/Jupyter) or calling the help()
    function:

    .. code:: python

        import kaic.plotting as kplot
        kplot.BigWigPlot? # Ipython/Jupyter
        help(kplot.BigWigPlot) # standard python


A few basic parameters such as a title and the aspect ratio are available for all
plot classes. The aspect ratio parameter is a floating point number between 0 and 1
that determines the height of the plot. A value of 1 results in a square plot,
.5 represents a plot that is half as high as it is wide.

The :class:`~kaic.plotting.plotter.GenomicFigure` provides a few convenience
parameters. Setting ticks_last=True for example removes tick labels from all
panels but the last one which makes the overall plot more compact.

Kaic plotting is ideally suited for programmatic generation of many plots or
dynamic assembly of multiple datasets in a single figure. In this example three
Hi-C datasets are visualized in a single figure:

.. code:: python

    import kaic.plotting as kplot
    hic_datasets = ["my_data1.hic", "my_data2.hic", my_data3.hic"]
    hic_plots = [kplot.HicPlot(h, max_dist=500000) for h in hic_datasets]
    gfig = kplot.GenomicFigure(hic_plots)
    fig, axes = gfig.plot("chr11:77400000-78600000")
    fig.show()

"""

from kaic.plotting.hic_plotter import HicPlot, HicPlot2D, HicComparisonPlot2D, HicSideBySidePlot2D, \
    HicSlicePlot, HicPeakPlot
from kaic.plotting.plotter import VerticalSplitPlot, GenomicVectorArrayPlot, GenomicFeaturePlot, GenomicRegionsPlot, \
    GenomicFeatureScorePlot, GenomicMatrixPlot, GenomicFigure, GenomicTrackPlot, BigWigPlot, GenePlot, \
    FeatureLayerPlot, GenomicDataFramePlot, HighlightAnnotation, VerticalLineAnnotation
from kaic.plotting.helpers import append_axes, absolute_wspace_hspace, SymmetricNorm, \
                                  style_ticks_whitegrid, LimitGroup

from kaic.plotting.colormaps import *
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_style("ticks")

plt.register_cmap(name='viridis', cmap=viridis)
plt.register_cmap(name='plasma', cmap=plasma)
plt.register_cmap(name='inferno', cmap=inferno)
plt.register_cmap(name='magma', cmap=magma)
plt.register_cmap(name='RdBuWhitespace_r', cmap=fc_cmap)
plt.register_cmap(name='germany', cmap=germany_cmap)
plt.register_cmap(name='white_red', cmap=white_red)
plt.register_cmap(name='white_red_r', cmap=white_red_r)
