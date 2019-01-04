from __future__ import division, print_function

import os.path

import numpy as np
import tables as t
from Bio import SeqIO, Restriction, Seq
from genomic_regions import RegionBased, GenomicRegion
from .general import FileGroup
from .tools.files import is_fasta_file
from .tools.general import create_col_index, RareUpdateProgressBar

try:
    from itertools import izip as zip
except ImportError:
    pass

from future.utils import string_types
from builtins import object
import logging
logger = logging.getLogger(__name__)


__all__ = ['Chromosome', 'Genome', 'RegionsTable', 'LazyGenomicRegion']


class Chromosome(object):
    """
    Chromosome data type.

    .. attribute:: name

        Name of the chromosome

    .. attribute:: length

        Length of the chromosome in base-pairs

    .. attribute:: sequence

        Base-pair sequence of DNA in the chromosome
    """

    def __init__(self, name=None, length=None, sequence=None):
        """
        Initialize chromosome

        :param name: Name of the chromosome
        :param length: Length of the chromosome in base-pairs
        :param sequence: Base-pair sequence of DNA in the chromosome
        """
        self.name = name.decode() if isinstance(name, bytes) else name
        self.length = length
        self.sequence = sequence.decode() if isinstance(sequence, bytes) else sequence
        if length is None and sequence is not None:
            self.length = len(sequence)
        if sequence is None and length is not None:
            self.length = length

    def __repr__(self):
        return "Name: %s\nLength: %d\nSequence: %s" % (self.name if self.name else '',
                                                       self.length if self.length else -1,
                                                       self.sequence[:20] + "..." if self.sequence else '')

    def __len__(self):
        """
        Get length of the chromosome.
        """
        return self.length

    def __getitem__(self, key):
        """
        Get object attributes by name
        """
        if key == 'name':
            return self.name
        if key == 'length':
            return self.length
        if key == 'sequence':
            return self.sequence

    @classmethod
    def from_fasta(cls, file_name, name=None, include_sequence=True):
        """
        Create a :class:`~Chromosome` from a FASTA file.

        This class method will load a FASTA file and convert it into
        a :class:`~Chromosome` object. If the FASTA file contains multiple
        sequences, only the first one will be read.

        :param file_name: Path to the FASTA file
        :param name: Chromosome name. If None (default), will be read
                     from the FASTA file header
        :param include_sequence: If True (default), stores the chromosome
                                 sequence in memory. Else, the sequence
                                 attribute will be set to None.
        :return: :class:`~Chromosome` if there is only a single FASTA
                 sequence in the file, list(:class:`~Chromosome`) if
                 there are multiple sequences.
        """
        with open(file_name, 'r') as fasta_file:
            fastas = SeqIO.parse(fasta_file, 'fasta')

            chromosomes = []
            for fasta in fastas:
                if include_sequence:
                    chromosome = cls(name if name else fasta.id, length=len(fasta), sequence=str(fasta.seq))
                else:
                    chromosome = cls(name if name else fasta.id, length=len(fasta))
                chromosomes.append(chromosome)

        if len(chromosomes) == 0:
            raise ValueError("File %s does not appear to be a FASTA file" % file_name)
        if len(chromosomes) == 1:
            return chromosomes[0]
        return chromosomes

    def get_restriction_sites(self, restriction_enzyme):
        """
        Find the restriction sites of a provided enzyme in this chromosome.

        Internally uses biopython to find RE sites.

        :param restriction_enzyme: The name of the restriction enzyme
                                   (e.g. HindIII)
        :return: List of RE sites in base-pairs (1-based)
        """
        logger.info("Calculating RE sites")
        try:
            re = getattr(Restriction, restriction_enzyme)
        except SyntaxError:
            raise ValueError("restriction_enzyme must be a string")
        except AttributeError:
            raise ValueError("restriction_enzyme string is not recognized: %s" % restriction_enzyme)

        return re.search(Seq.Seq(self.sequence))


class LazyGenomicRegion(GenomicRegion):
    def __init__(self, row, ix=None, auto_update=True):
        self.reserved = {'_row', 'static_ix', 'strand', 'auto_update', 'attributes'}
        self._row = row
        self.static_ix = ix
        self.auto_update = auto_update

    def __getattr__(self, item):
        if item == 'reserved' or item in self.reserved:
            return object.__getattribute__(self, item)
        try:
            value = self._row[item]
            value = value.decode() if isinstance(value, bytes) else value
            return value
        except KeyError:
            raise AttributeError

    def __setattr__(self, key, value):
        if key == 'reserved' or key in self.reserved:
            super(LazyGenomicRegion, self).__setattr__(key, value)
        else:
            self._row[key] = value
            if self.auto_update:
                self.update()

    def update(self):
        self._row.update()

    @property
    def strand(self):
        try:
            return self._row["strand"]
        except KeyError:
            return None

    @property
    def ix(self):
        if self.static_ix is None:
            return self._row["ix"]
        return self.static_ix

    @property
    def attributes(self):
        return self._row.tables.colnames


class RegionBasedWithBins(RegionBased):
    def __init__(self):
        super(RegionBasedWithBins, self).__init__()

    @property
    def chromosome_bins(self):
        """
        Returns a dictionary of chromosomes and the start
        and end index of the bins they cover.

        Returned list is range-compatible, i.e. chromosome
        bins [0,5] cover chromosomes 1, 2, 3, and 4, not 5.
        """
        return self._chromosome_bins()

    def _chromosome_bins(self):
        chr_bins = {}
        for r in self.regions:
            if chr_bins.get(r.chromosome) is None:
                chr_bins[r.chromosome] = [r.ix, r.ix + 1]
            else:
                chr_bins[r.chromosome][1] = r.ix + 1
        return chr_bins

    @property
    def bin_size(self):
        """
        Return the size of the first region in the dataset.

        Assumes all regions have equal size.

        :return: int
        """
        return len(self.regions[0]) + 1

    def distance_to_bins(self, distance):
        """
        Convert base pairs to fraction of bins.

        :param distance: distance in base pairs
        :return: float, distance as fraction of bin size
        """
        bin_size = self.bin_size
        bin_distance = int(distance / bin_size)
        if distance % bin_size > 0:
            bin_distance += 1
        return bin_distance

    def bins_to_distance(self, bins):
        """
        Convert fraction of bins to base pairs

        :param bins: float, fraction of bins
        :return: int, base pairs
        """
        return int(self.bin_size * bins)

    def region_bins(self, region):
        start_ix = None
        end_ix = None
        for i, r in enumerate(self.regions(region)):
            ix = getattr(r, 'ix', i)
            if start_ix is None:
                start_ix = ix
            end_ix = ix + 1
        return slice(start_ix, end_ix, 1)


class RegionsTable(RegionBasedWithBins, FileGroup):
    """
    PyTables Table wrapper for storing genomic regions.

    This class is inherited by objects working with lists of genomic
    regions, such as equidistant bins along chromosomes in a genome
    (:class:`~Hic`) or restriction fragments of genomic DNA
    (:class:`~kaic.construct.seq.FragmentMappedReadPairs`)
    """

    _classid = 'REGIONSTABLE'

    class RegionDescription(t.IsDescription):
        """
        Description of a genomic region for PyTables Table
        """
        ix = t.Int32Col(pos=0)
        chromosome = t.StringCol(100, pos=1)
        start = t.Int64Col(pos=2)
        end = t.Int64Col(pos=3)
        strand = t.Int8Col(pos=4)
        _mask_ix = t.Int32Col(pos=5)

    def __init__(self, file_name=None, mode='a', tmpdir=None,
                 additional_fields=None, _table_name_regions='regions'):
        """
        Initialize region table.

        :param file_name: Path to file
        :param _table_name_regions: (Internal) name of the HDF5
                                    node that stores data for this
                                    object
        """
        self._regions_dirty = False

        file_exists = False
        if file_name is not None and os.path.exists(os.path.expanduser(file_name)):
            file_exists = True

        FileGroup.__init__(self, _table_name_regions, file_name, mode=mode, tmpdir=tmpdir)

        if file_exists and mode != 'w':
            self._regions = self._group.regions
        else:
            basic_fields = dict()
            hidden_fields = dict()
            for field, description in RegionsTable.RegionDescription().columns.copy().items():
                if field.startswith('_'):
                    hidden_fields[field] = description
                else:
                    basic_fields[field] = description

            current = len(basic_fields)
            if additional_fields is not None:
                if not isinstance(additional_fields, dict) and issubclass(additional_fields, t.IsDescription):
                    # IsDescription subclass case
                    additional_fields = additional_fields.columns

                # add additional user-defined fields
                for key, value in sorted(additional_fields.items(),
                                         key=lambda x: x[1]._v_pos if x[1]._v_pos is not None else 1):
                    if key not in basic_fields:
                        value._v_pos = current
                        current += 1
                        basic_fields[key] = value
            # add hidden fields
            for key, value in sorted(hidden_fields.items(),
                                     key=lambda x: x[1]._v_pos if x[1]._v_pos is not None else 1):
                value._v_pos = current
                current += 1
                basic_fields[key] = value

            self._regions = t.Table(self._group, 'regions', basic_fields)

            # create indexes
            create_col_index(self._regions.cols.ix)
            create_col_index(self._regions.cols.start)
            create_col_index(self._regions.cols.end)

    def _flush_regions(self):
        if self._regions_dirty:
            self._regions.flush()
            self._regions_dirty = False

    def flush(self):
        self._flush_regions()

    def _add_region(self, region, *args, **kwargs):
        self._regions_dirty = True
        ix = getattr(self.meta, 'max_region_ix', -1) + 1

        # actually append
        row = self._regions.row
        row['ix'] = ix
        row['chromosome'] = region.chromosome
        row['start'] = region.start
        row['end'] = region.end
        if hasattr(region, 'strand') and region.strand is not None:
            row['strand'] = region.strand

        for name in self._regions.colnames[5:]:
            if hasattr(region, name):
                row[name] = getattr(region, name)

        row.append()

        if ix > getattr(self.meta, 'max_region_ix', -1):
            self.meta['max_region_ix'] = ix

        return ix

    def add_regions(self, regions):
        """
        Bulk insert multiple genomic regions.

        :param regions: List (or any iterator) with objects that
                        describe a genomic region. See
                        :class:`~RegionsTable.add_region` for options.
        """

        for i, region in enumerate(regions):
            self.add_region(region, flush=False)

        self._flush_regions()

    def region_data(self, key, value=None):
        """
        Retrieve or add vector-data to this object. If there is existing data in this
        object with the same name, it will be replaced

        :param key: Name of the data column
        :param value: vector with region-based data (one entry per region)
        """
        if key not in self._regions.colnames:
            raise KeyError("{} is unknown region attribute".format(key))

        if value is not None:
            for i, row in enumerate(self._regions):
                row[key] = value[i]
                row.update()
            self._flush_regions()

        return (row[key] for row in self._regions)

    def _get_region_ix(self, region):
        """
        Get index from other region properties (chromosome, start, end)
        """
        condition = "(start == %d) & (end == %d) & (chromosome == b'%s')"
        condition %= region.start, region.end, region.chromosome
        for res in self._regions.where(condition):
            return res["ix"]
        return None

    def _row_to_region(self, row, lazy=False, auto_update=True):
        if lazy:
            return LazyGenomicRegion(row, auto_update=auto_update)

        kwargs = {}
        for name in self._regions.colnames:
            if name not in RegionsTable.RegionDescription().columns.keys():
                value = row[name]
                value = value.decode() if isinstance(value, bytes) else value
                kwargs[name] = value

        try:
            mask_ix = row['_mask_ix']
        except (KeyError, ValueError):
            mask_ix = 0

        return GenomicRegion(chromosome=row["chromosome"].decode(), start=row["start"],
                             end=row["end"], ix=row["ix"], _mask_ix=mask_ix, **kwargs)

    def _region_iter(self, lazy=False, auto_update=True, *args, **kwargs):
        for row in self._regions:
            yield self._row_to_region(row, lazy=lazy, auto_update=auto_update)

    def _region_subset(self, region, lazy=False, auto_update=True, *args, **kwargs):
        for row in self._subset_rows(region):
            sub_region = self._row_to_region(row, lazy=lazy, auto_update=auto_update)
            yield sub_region

    def _get_regions(self, key, *args, **kwargs):
        res = self._regions[key]

        if isinstance(res, np.ndarray):
            regions = []
            for region in res:
                regions.append(self._row_to_region(region))
            return regions
        else:
            return self._row_to_region(res)

    def _region_len(self):
        return len(self._regions)

    def _subset_rows(self, key):
        """
        Iterate over a subset of regions given the specified key.

        :param key: A :class:`~kaic.data.genomic.GenomicRegion` object,
                    or a list of the former. Also accepts slices and integers
        :return: Iterator over the specified subset of regions
        """
        if isinstance(key, slice):
            for row in self._regions.where("(ix >= {}) & (ix < {})".format(key.start, key.stop)):
                yield row
        elif isinstance(key, int):
            yield self._regions[key]
        elif isinstance(key, list) and len(key) > 0 and isinstance(key[0], int):
            for ix in key:
                yield self._regions[ix]
        else:
            if isinstance(key, string_types):
                key = GenomicRegion.from_string(key)

            if isinstance(key, GenomicRegion):
                keys = [key]
            else:
                keys = key

            for k in keys:
                if isinstance(k, string_types):
                    k = GenomicRegion.from_string(k)

                query = '('
                if k.chromosome is not None:
                    query += "(chromosome == b'%s') & " % k.chromosome
                if k.end is not None:
                    query += "(start <= %d) & " % k.end
                if k.start is not None:
                    query += "(end >= %d) & " % k.start
                if query.endswith(' & '):
                    query = query[:-3]
                query += ')'

                if len(query) == 2:
                    for row in self._regions:
                        yield row
                else:
                    for row in self._regions.where(query):
                        yield row


class Genome(FileGroup):
    """
    Class representing a collection of chromosomes.

    Extends the :class:`~RegionsTable` class and provides
    all the expected functionality. Provides some convenience batch
    methods that call :class:`~Chromosome` methods for every
    chromosome in this object.

    This object can be saved to file.
    """

    class ChromosomeDefinition(t.IsDescription):
        name = t.StringCol(255, pos=0)
        length = t.Int64Col(pos=1)

    def __init__(self, file_name=None, chromosomes=None, mode='a', tmpdir=None,
                 _table_name_chromosomes='chromosomes'):
        """
        Build :class:`~Genome` from a list of chromosomes or load
        previously saved object.

        :param file_name: Path of the file to load or to save to.
        :param chromosomes: List of chromosomes to load into this
                            object.
        """
        FileGroup.__init__(self, _table_name_chromosomes, file_name, mode=mode, tmpdir=tmpdir)

        # check if this is an existing regions file
        try:
            self._sequences = self._group.sequences
        except t.NoSuchNodeError:
            self._sequences = self.file.create_vlarray(self._group, 'sequences', t.VLStringAtom())

        try:
            self._chromosome_table = self._group.chromosomes
        except t.NoSuchNodeError:
            try:
                self._chromosome_table = self.file.create_table(self._group, 'chromosomes',
                                                                Genome.ChromosomeDefinition)
            except t.FileModeError:
                self._chromosome_table = None
                pass

        if chromosomes is not None:
            if isinstance(chromosomes, Chromosome):
                chromosomes = [chromosomes]

            for chromosome in chromosomes:
                self.add_chromosome(chromosome)

    def chromosomes(self):
        return self._names

    @property
    def _names(self):
        if self._chromosome_table is None:
            try:
                return self.meta['chromosome_names']
            except KeyError:
                return []
        else:
            return [row['name'].decode() if isinstance(row['name'], bytes) else row['name']
                    for row in self._chromosome_table]

    @_names.setter
    def _names(self, names):
        if self._chromosome_table is None:
            self.meta['chromosome_names'] = names
        else:
            counter = 0
            for i, row in enumerate(self._chromosome_table):
                row['name'] = names[i]
                row.update()
                counter += 1
            for i in range(counter, len(names)):
                self._chromosome_table.row['name'] = names[i]
                self._chromosome_table.row.append()
        self._chromosome_table.flush()

    @property
    def _lengths(self):
        if self._chromosome_table is None:
            try:
                return self.meta['chromosome_lengths']
            except KeyError:
                return []
        else:
            return [row['length'] for row in self._chromosome_table]

    @_lengths.setter
    def _lengths(self, lengths):
        if self._chromosome_table is None:
            self.meta['chromosome_lengths'] = lengths
        else:
            counter = 0
            for i, row in enumerate(self._chromosome_table):
                row['length'] = lengths[i]
                row.update()
                counter += 1
            for i in range(counter, len(lengths)):
                self._chromosome_table.row['length'] = lengths[i]
                self._chromosome_table.row.append()
        self._chromosome_table.flush()
        self.meta['chromosome_lengths'] = lengths

    @classmethod
    def from_folder(cls, folder_name, file_name=None, exclude=None,
                    include_sequence=True, tmpdir=None):
        """
        Load every FASTA file from a folder as a chromosome.

        :param folder_name: Path to the folder to load
        :param file_name: File to save Genome object to
        :param exclude: List or set of chromosome names that
                        should NOT be loaded
        :param include_sequence: If True, will save the
                                 chromosome sequences in the
                                 Genome object
        """
        chromosomes = []
        folder_name = os.path.expanduser(folder_name)
        for f in os.listdir(folder_name):
            try:
                chromosome = Chromosome.from_fasta(folder_name + "/" + f,
                                                   include_sequence=include_sequence)
                logger.info("Adding chromosome %s" % chromosome.name)
                if exclude is None:
                    chromosomes.append(chromosome)
                elif chromosome.name not in exclude:
                    chromosomes.append(chromosome)
            except (ValueError, IOError):
                pass

        return cls(chromosomes=chromosomes, file_name=file_name, tmpdir=tmpdir)

    @classmethod
    def from_string(cls, genome_string, file_name=None, tmpdir=None, mode='a'):
        """
        Convenience function to load a :class:`~Genome` from a string.

        :param genome_string: Path to FASTA file, path to folder with
                              FASTA files, comma-separated list of
                              paths to FASTA files, path to HDF5 file
        :param file_name: Path to save file
        :return: A :class:`~Genome` object
        """
        # case 1: FASTA file = Chromosome
        if is_fasta_file(genome_string):
            chromosomes = Chromosome.from_fasta(genome_string)
            genome = cls(chromosomes=chromosomes, file_name=file_name, tmpdir=tmpdir)
        # case 2: Folder with FASTA files
        elif os.path.isdir(genome_string):
            genome = cls.from_folder(genome_string, file_name=file_name, tmpdir=tmpdir)
        # case 3: path to HDF5 file
        elif os.path.isfile(genome_string):
            genome = cls(genome_string, tmpdir=tmpdir, mode=mode)
        # case 4: List of FASTA files
        else:
            chromosome_files = genome_string.split(',')
            chromosomes = []
            for chromosome_file in chromosome_files:
                chromosome = Chromosome.from_fasta(os.path.expanduser(chromosome_file))
                chromosomes.append(chromosome)
            genome = cls(chromosomes=chromosomes, file_name=file_name, tmpdir=tmpdir)

        return genome

    def __getitem__(self, key):
        """
        Get Genome table subsets.

        If the result is one or more rows, they will be converted to
        :class:`~Chromosome` objects, if the result is a column, it
        will be returned without conversion.
        """
        names = self._names
        lengths = self._lengths

        if isinstance(key, string_types):
            key = names.index(key)

        if isinstance(key, int):
            return Chromosome(name=names[key], length=lengths[key], sequence=self._sequences[key])
        elif isinstance(key, slice):
            l = []
            start = key.start if key.start is not None else 0
            stop = key.stop if key.stop is not None else len(names)
            step = key.step if key.step is None else 1

            for i in range(start, stop, step):
                c = Chromosome(name=names[i], length=lengths[i], sequence=self._sequences[i])
                l.append(c)
            return l
        else:
            l = []
            for i in key:
                if isinstance(i, string_types):
                    i = names.index(i)
                c = Chromosome(name=names[i], length=lengths[i], sequence=self._sequences[i])
                l.append(c)
            return l

    def __len__(self):
        return len(self._names)

    def __iter__(self):
        """
        Get iterator over :class:`~Chromosome` objects.
        """
        this = self

        class Iter(object):
            def __init__(self):
                self.current = 0

            def __iter__(self):
                self.current = 0
                return self

            def __next__(self):
                if self.current >= len(this):
                    raise StopIteration
                self.current += 1
                return this[self.current - 1]

        return Iter()

    def add_chromosome(self, chromosome):
        """
        Add a :class:`~Chromosome` to this object.

        Will choose suitable defaults for missing attributes.

        :param chromosome: :class:`~Chromosome` object or similar
                           object (e.g. dict) with the same fields
        """
        i = len(self._names)

        n = str(i)
        if chromosome.name is not None:
            n = chromosome.name

        l = 0
        if chromosome.length is not None:
            l = chromosome.length

        s = ''
        if chromosome.sequence is not None:
            s = chromosome.sequence
            if l == 0:
                l = len(s)

        self._chromosome_table.row['name'] = n
        self._chromosome_table.row['length'] = l
        self._chromosome_table.row.append()

        # self._names = self._names + [n]
        # self._lengths = self._lengths + [l]
        self._sequences.append(s)
        self._sequences.flush()
        self._chromosome_table.flush()

    def get_regions(self, split, file_name=None, chromosomes=None):
        """
        Extract genomic regions from genome.

        Provides two options:

        - Splits chromosomes at restriction sites if the split
          parameter is the name of a restriction enzyme.

        - Splits chromosomes at equi-distant points if split
          is an integer

        :param split: Name of a restriction enzyme or positive
                      integer
        :param file_name: Name of a file if the result of this
                          method should be saved to file
        :param chromosomes: List of chromosome names to include. Default: all
        :return: :class:`~GenomicRegions`
        """

        regions = RegionsTable(file_name=file_name)
        for chromosome in self:
            if chromosomes is not None and chromosome.name not in chromosomes:
                continue
            split_locations = []
            if isinstance(split, string_types):
                split_locations = chromosome.get_restriction_sites(split)
            elif isinstance(split, int):
                for i in range(split, len(chromosome) - 1, split):
                    split_locations.append(i)
            else:
                for i in split:
                    split_locations.append(i)

            for i in range(0, len(split_locations)):
                if i == 0:
                    region = GenomicRegion(start=1, end=split_locations[i], chromosome=chromosome.name)
                else:
                    region = GenomicRegion(start=split_locations[i - 1] + 1,
                                           end=split_locations[i], chromosome=chromosome.name)

                regions.add_region(region, flush=False)

            # add last node
            if len(split_locations) > 0:
                region = GenomicRegion(start=split_locations[len(split_locations) - 1] + 1,
                                       end=chromosome.length, chromosome=chromosome.name)
            else:
                region = GenomicRegion(start=1, end=chromosome.length, chromosome=chromosome.name)
            regions.add_region(region, flush=True)

        return regions

    def sub_sequence(self, chromosome, start=None, end=None):
        if start is not None:
            selection_region = GenomicRegion(chromosome=chromosome, start=start, end=end)
        elif isinstance(chromosome, GenomicRegion):
            selection_region = chromosome
        else:
            selection_region = GenomicRegion.from_string(chromosome)

        res_chromosome = self[selection_region.chromosome]
        if selection_region.start is None:
            return res_chromosome.sequence
        return res_chromosome.sequence[selection_region.start - 1:selection_region.end]
