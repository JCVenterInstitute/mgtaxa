### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the MGTAXA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


"""Application for building collections of IMMs/ICMs and scoring against them"""

from MGT.Imm import *
from MGT.Taxa import *
from MGT.Svm import *
from MGT.App import *
from MGT.DirStore import *
from MGT.SeqDbFasta import *
import UUID

from MGT.Hdf import *

class ImmScores(object):
    """Class that stores and manipulates Imm scores for a set of samples and a set of Imms.
    This is an abstract class that describes the interface.
    """

    def __init__(self,fileName,mode,**kw):
        """Constructor.
        In this default constructor, all parameters are assigned as attributes 
        to the object (by reference) and used later when the actual data 
        operations are requested.
        @param fileName name of the new object in storage
        @param mode One of w|r|c with a semantic similar to the open() builtin
        """
        self.fileName = fileName
        self.mode = mode
        for key,val in kw.items():
            setattr(self,key,val)

    def appendScore(self,idScore,score):
        """Append to the dataset a score vector for one Imm.
        @param idScore Id of the Imm
        @param score numpy.recarray(names="id","score")
        """
        pass

    def close(self):
        """Semantics is similar to a close() method on the file object (can be a noop)"""
        pass
    
    def catScores(self,fileNames,idScoreSel=None):
        """Concatenate into self a sequence of ImmScores objects representing different or same idScores for the same set of samples.
        @param fileNames sequence of object names to be concatenated
        @param idScoreSel optional sequence of all idScores that are expected to be present in the inputs;
        KeyError exception will be raised if any is missing"""
        pass

    def makeIdDtype(self,valElem):
        """Generate the most appropriate numpy.dtype for ID based on a sample element.
        @param valElem One in-memory ID element value - can be Python native type or numpy array element.
        If valElem has a dtype attribute, it will be returned unchanged.
        Fixed-length string type will be returned for a string value; for the others default numpy.dtype
        constructor will be applied"""
        if hasattr(valElem,"dtype"):
            return valElem.dtype
        defDtype = n.dtype(type(valElem))
        if defDtype.kind == "S":
            return idDtype
        return defDtype

class ImmScoresHdf(ImmScores):
    """Base for implementations of ImmScores which use HDF5 as storage.
    """
    
    def setLenSamp(self,lenSamp,sourceType="recarray"):
        """Create and assign sample length dataset.
        @param lenSamp source of sample length data
        @param sourceType type of lenSamp: 
            recarray - Numpy recarray("id","len")
            iter_recarrays - iterator of recarrays
        In either case, the order of IDs in the source must match the order of IDs
        already stored in this object.
        """
        g = self.getData()
        if sourceType == "recarray":
            assert n.all(g.idSamp[:] == lenSamp["id"]),"Sample IDs do not match for sample length array"
            self.hdfFile.createArray(g, 'lenSamp', lenSamp["len"],"Sample length")
        elif sourceType == "iter_recarrays":
            self.hdfFile.createArray(g, 
                    'lenSamp', 
                    n.zeros(len(g.idSamp),dtype="i8"),
                    "Sample length")
            block_start = 0
            for block in lenSamp:
                block_end = block_start + len(block)
                assert (g.idSamp[block_start:block_end] == block["id"]).all(),\
                        "Sample IDs do not match for sample length block"
                g.lenSamp[block_start:block_end] = block["len"]
                block_start = block_end

    
    def getKind(self):
        return self.getData()._v_attrs.kind
    
    def getData(self):
        if not hasattr(self,"hdfFile"):
            self.open()
        return self.hdfFile.root.immScores
    
    def open(self):
        self.hdfFile = pt.openFile(self.fileName, mode = self.mode)

    def close(self):
        """Semantics is similar to a close() method on the file object (can be a noop)"""
        if hasattr(self,"hdfFile"):
            self.hdfFile.close()

class ImmScoresReducedHdf(ImmScoresHdf):
    """Implementation of ImmScores that does score reduction and uses HDF5 as storage.
    Reduction means that at every appendScore call, only the best scores and
    associated Imm IDs are retained, in order to minimize intermediate storage.
    
    """
    
    #TODO: switch to using chunks with interface
    # iNextStart appendScore(self,idScore,score=iter of rec arrays,iStart,nScoresTotal)
    def appendScore(self,idScore,score):
        """Append to the dataset a score vector for one Imm.
        @param idScore Id of the score from a set of Imms. 
        Repeated calls with the same idScore
        are OK - the maximum value will be retained.
        @param score numpy.recarray(names=("id","score"))
        """
        if not self.initStorageIf(idScore,score):
            #existed already with data
            g = self.getData()
            #For PyTables datasets, the indexing operator [] is never called
            #implicitely unlike for Numpy arrays, hence [:] below.
            #Note that any [] also returns a Numpy array in memory, so beware of
            #data size.
            assert n.all(score["id"] == g.idSamp[:]),"Sample IDs do not match for scores"
            whereNewIsLarger = n.where(score["score"] > g.score[:])
            g.score[whereNewIsLarger] = score["score"][whereNewIsLarger] #Do I really need rhs selection?
            g.idScore[whereNewIsLarger] = idScore


    def initStorageIf(self,idScore,score):
        if not hasattr(self,"hdfFile"):
            self.open()
            f = self.hdfFile
            g = f.createGroup(f.root,"immScores")
            g._v_attrs.kind = "ImmScoresReduced"
            f.createArray(g, 'idSamp', score["id"],"Sample ID")
            idScoreArr = n.zeros(len(score),dtype=self.makeIdDtype(idScore))
            idScoreArr[:] = idScore
            f.createArray(g, 'idScore', idScoreArr, "Score ID")
            f.createArray(g, 'score', score["score"],"Score")
            f.flush()
            return True
        else:
            return False

    
    def catScores(self,fileNames,idScoreSel=None):
        """Concatenate into self a sequence of ImmScores objects representing different Imms for the same set of samples.
        @param fileNames sequence of object names to be concatenated
        @param idScoreSel optional sequence of all idScores that are expected to be present in the inputs;
        KeyError exception will be raised if any is missing.
        
        @post Datatypes will be determined from the first file in fileNames"""
        assert len(fileNames) > 0,"Need a non-empty sequence of input object names"
        firstFileName = fileNames[0]
        pt.copyFile(firstFileName,self.fileName, overwrite=True)
        self.mode = "r+"
        self.open()
        f = self.hdfFile
        g = f.root.immScores
        for fileName in fileNames[1:]:
            fo = pt.openFile(fileName,mode="r")
            go = fo.root.immScores
            #For PyTables datasets, the indexing operator [] is never called
            #implicitely unlike for Numpy arrays, hence [:] below.
            #Note that any [] also returns a Numpy array in memory, so beware of
            #data size.
            assert n.all(go.idSamp[:] == g.idSamp[:]),"Sample IDs do not match for scores"
            whereNewIsLarger = n.where(go.score[:] > g.score[:])
            g.score[whereNewIsLarger] = go.score[whereNewIsLarger] #Do I really need rhs selection?
            g.idScore[whereNewIsLarger] = go.idScore[whereNewIsLarger]
            if "lenSamp" not in g and "lenSamp" in go:
                go.lenSamp._f_copy(g)
            fo.close()
        f.flush()

class ImmScoresDenseMatrixHdf(ImmScoresHdf):
    """Implementation of ImmScores that accumulates scores in a dense matrix and uses HDF5 as storage.
    The columns are samples, the rows are score IDs. Score IDs can be repeated in appendScore() and
    catScores() methods, in which case the maximum value is stored for each (idSample,idScore) cell.
    """

    def appendScore(self,idScore,score):
        """Append to the dataset a score vector for one Imm.
        @param idScore Id of the score from a set of Imms. Repeated
        calls with the same idScore are OK - the maximum value will
        be retained for each sample.
        @param score numpy.recarray(names=("id","score"))
        """
        self.initStorageIf(score)
        g = self.getData()
        #For PyTables datasets, the indexing operator [] is never called
        #implicitely unlike for Numpy arrays, hence [:] below.
        #Note that any [] also returns a Numpy array in memory, so beware of
        #data size.
        assert n.all(score["id"] == g.idSamp[:]),"Sample IDs do not match for scores"
        self._appendScoreInternal(g,idScore,score["score"])       
        g.score.flush()

    def _appendScoreInternal(self,g,idScore,score):
        """Internal method w/o checks to call from both appendScore() and catScores()"""
        idScorePos = self.idScoreInd[idScore]
        if g.idScoreSeen[idScorePos]:
            whereNewIsLarger = n.where(score > g.score[idScorePos,:])
            g.score[idScorePos,whereNewIsLarger[0]] = score[whereNewIsLarger] #Do I really need rhs selection?
        else:
            g.score[idScorePos,:] = score
            g.idScoreSeen[idScorePos] = True


    def initStorageIf(self,score):
        if not hasattr(self,"hdfFile"):
            assert len(self.idScore)
            self.initStorage(idSamp=score["id"],
                    idScore=n.asarray(self.idScore,dtype=self.makeIdDtype(self.idScore[0])),
                    dtype=score["score"].dtype)
            return True
        else:
            return False
    
    def initStorage(self,idSamp,idScore,dtype):
        assert isUniqueArray(idScore), "idScore must be an array with unique elements"
        self.open()
        f = self.hdfFile
        g = f.createGroup(f.root,"immScores")
        g._v_attrs.kind = "ImmScoresDenseMatrix"
        f.createArray(g, 'idSamp', idSamp,"Sample ID")
        f.createArray(g, 'idScore', idScore, "Score ID")
        #We need to find and assign a max between existing
        #and current score for a given idScore. To avoid
        #setting an entire matrix to -INF at creation time,
        #we keep a bool array that remembers if the row
        #for a given idScore is not NULL. This array is also
        #used in a pre-condition check when we concatenate
        #several matrices.
        idScoreSeen = n.zeros(len(idScore),dtype=bool)
        f.createArray(g, 'idScoreSeen', idScoreSeen, "Did we see Score ID?")
        self.idScoreInd = dict(((x[1],x[0]) for x in enumerate(idScore)))
        #Strangely, simple Array can only be created from a data object,
        #and so it should always fit into RAM. Hence, we use CArray here.
        #We put Imms into rows, so that adding Imms is efficient.
        #During classifcation, reduction will be done along columns (samples),
        #and we will need to do in blocks of rows (or load entire matrix at once)
        #because reading by single columns will be very I/O inefficient.
        #There are various chunkshape tricks to play for making a compromise
        #between reading and writing along different dimensions, but we are
        #not trying them yet. The PyTables author's advice is to use a dataset
        #copy() method to copy into a new one with the chunksize that is optimized
        #for the required access pattern.
        f.createCArray(g, 
                'score', 
                atom=pt.Atom.from_dtype(dtype),
                shape=(len(idScore),len(idSamp)),
                title="Score")

    def catScores(self,fileNames,idScoreSel=None):
        """Concatenate into self a sequence of ImmScores objects with different or same idScores for the same set of samples.
        @param fileNames sequence of object names to be concatenated
        @param idScoreSel optional sequence of all idScores that are expected to be present in the inputs;
        KeyError exception will be raised if any is missingi.
        
        @post Datatypes will be determined from the first file in fileNames."""
        assert len(fileNames) > 0,"Need a non-empty sequence of input object names"
        idSamp = None
        lenSamp = None
        idScore = []
        dtype = None
        for (iFile,fileName) in enumerate(fileNames):
            fo = pt.openFile(fileName,mode="r")
            go = fo.root.immScores
            assert n.all(go.idScoreSeen[:]),"Pre-condition for concatenation is that all scores are assigned in all inputs"
            if iFile == 0:
                idSamp = go.idSamp[:]
                dtype = go.score.dtype
            else:
                assert n.all(go.idSamp[:] == idSamp[:]),"Sample IDs do not match for scores"
                assert dtype == go.score.dtype,"Dtypes do not match for concatenated datasets"
            idScore.append(go.idScore[:])
            fo.close()
        #Leave only unique score IDs in the order they first appeared in the concatenated
        #set of IDs. This will minimize random seeks during matrix concatenation, especially
        #for a typical case when only a few IDs are repeated in different datasets.
        idScore = n.asarray(unique(n.concatenate(idScore),stable=True),dtype=idScore[0].dtype)

        self.mode = "w"
        self.initStorage(idSamp=idSamp,
                idScore=idScore,
                dtype=dtype)

        f = self.hdfFile
        g = f.root.immScores
        for (iFile,fileName) in enumerate(fileNames):
            fo = pt.openFile(fileName,mode="r")
            go = fo.root.immScores
            goScore = go.score
            goIdScore = go.idScore
            for pos in xrange(len(goScore)):
                self._appendScoreInternal(g,goIdScore[pos],goScore[pos])
            if "lenSamp" not in g and "lenSamp" in go:
                go.lenSamp._f_copy(g)
            fo.close()
            g.score.flush()
        
        assert n.all(g.idScoreSeen[:]),"Post-condition for concatenation is that all scores are assigned in the output"


def openImmScores(opt,*l,**kw):
    """Factory method to make a proper derivative of ImmScores class based on App options.
    """
    if opt.reduceScoresEarly:
        typeDescr = "reduced"
    else:
        typeDescr = "dense"
    if typeDescr == "reduced":
        return ImmScoresReducedHdf(*l,**kw)
    elif typeDescr == "dense":
        return ImmScoresDenseMatrixHdf(*l,**kw)
    else:
        raise ValueError("Unknown 'typeDescr' value: %s" % (typeDescr,))

class ImmStore(DirKeyStore):
    
    objSfx = ".imm"
    
    def getImmPath(self,id):
        return self.getFilePathById(id)
    
    def listImmIds(self,iterPaths=None):
        """List IMM IDs either from this store or from the externally provided iterable"""
        return self.listIds(iterPaths=iterPaths)
    
    def listImmIdsWithIdScoreIdent(self,iterPaths=None):
        """Return a default mapping of model IDs to score IDs as (immId,immId) identity"""
        return [ (x,x) for x in self.listImmIds(iterPaths=iterPaths) ]
    
    def listSeqDbIds(self,iterPaths=None):
        seq_db_ids = set()
        for (id,meta) in self.iterMetaData(iterPaths=iterPaths):
            seq_db_ids |= set(meta["seq_db_ids"])
        return seq_db_ids

class ImmStoreWithTaxids(ImmStore):

    def listImmIdsWithTaxids(self,iterPaths=None):
        return list(((id,meta["taxid"]) for (id,meta) in self.iterMetaData(iterPaths=iterPaths)))
    
    def listTaxids(self,iterPaths=None):
        return list(set(meta["taxid"] for (id,meta) in self.iterMetaData(iterPaths=iterPaths)))
         
    def listTaxidsWithLeafModels(self,iterPaths=None):
        return list(set(meta["taxid"] for (id,meta) in self.iterMetaData(iterPaths=iterPaths) if meta["is_leaf"]))

def loadTrainModelsDescr(inp):
    """Return an iterator to model description records from JSON file.
    @param inp file name; the format example is
    test_data/fasta/generic.mod.train.json
    and the description is in
    doc/running.md
    @return iterator of records
    """
    with closing(openCompressed(inp,"r")) as inp:
        #json.load() loads entire file in memory
        #anyway, but we return it like an iterator
        #in case we switch to parsing stream of json records
        #in the future
        for rec in json.load(inp)["mgt_mod_descr"]:
            yield rec

def estimateNBatchesForScoring(
        nModels,
        inpSeq,
        inpSeqDbIds=None,
        totalSeqScanPerBatch=1024**3,
        maxDiskUse=128*1024**3,
        reduceScoresEarly=True):
    """Return the best estimated number of model batches"""
    if SeqDbFasta.isStore(inpSeq):
        inpSeq = SeqDbFasta.open(inpSeq,"r")
        if inpSeqDbIds is not None:
            if is_string(inpSeqDbIds):
                inpSeqDbIds = load_config_json(inpSeqDbIds)
        totalSeqLen = inpSeq.seqLengthsSumTotal(inpSeqDbIds)
        totalSeqCount = inpSeq.seqCountTotal(inpSeqDbIds)
    else:
        (totalSeqLen,totalSeqCount) = estimateFastaLengthAndCountTotal(inpSeq)
    if not (totalSeqLen and totalSeqCount):
        return 1
    maxDiskPerSeq = maxDiskUse / totalSeqCount
    targetBatches = max(totalSeqLen*nModels/totalSeqScanPerBatch,1)
    if reduceScoresEarly:
        diskPerSeqPerBatch = 2*maxIdLen + 4
        maxBatches = max(maxDiskPerSeq / diskPerSeqPerBatch,1)
    else:
        #intermediate datasets together is the final matrix split
        #into nBatches along columns, so the space is only wasted
        #on extra seqid per row in each batch
        maxBatches = max((maxDiskPerSeq - 4*nModels)/maxIdLen,1)
    nBatches = min(targetBatches,maxBatches)
    return nBatches




class ImmApp(App):
    """App-derived class for building collections of IMMs/ICMs and scoring against them"""

    batchDepModes = ("score","train")

    maxSeqIdLen = UUID.maxIdLen
    maxSeqPartIdLen = UUID.maxIdLen

    ## Degenerate alphabet symbols (IMMs work only for nucleotide sequences)
    degenSymb = "nN"

    scoreSfx = ".score"

    @classmethod
    def parseCmdLinePost(klass,options,args,parser):
        opt = options
        opt.setIfUndef("immDb","imm")
        opt.setIfUndef("nImmBatches",-1)
        opt.setIfUndef("trainMaxLenSampModel",10**9/2) #1G with rev-compl
        if not opt.isUndef("immIdToSeqIds"):
            opt.setIfUndef("immIds",opt.immIdToSeqIds)
        if not opt.isUndef("outDir"):
            opt.setIfUndef("outScoreComb",pjoin(opt.outDir,"combined"+klass.scoreSfx))
        opt.setIfUndef("inpSeqDbIds",pjoin(opt.cwd,"inp-seq-db-ids.json"))

    def initWork(self,**kw):
        opt = self.opt
        self.taxaTree = None #will be lazy-loaded
        self.seqDb = None #will be lazy-loaded
        self.store = SampStore.open(path=self.opt.get("cwd",os.getcwd()))
        self.immStore = ImmStore.open(path=self.opt.immDb)
        if opt.mode == "score":
            if opt.isUndef("immIds"):
                opt.immIds = pjoin(opt.cwd,"imm-ids.pkl")
                dumpObj(self.immStore.listImmIdsWithIdScoreIdent(),opt.immIds)

    def doWork(self,**kw):
        opt = self.opt
        if opt.mode == "train":
            return self.trainMany(**kw)
        elif opt.mode == "train-one":
            return self.trainOne(**kw)
        elif opt.mode == "score":
            return self.scoreMany(**kw)
        elif opt.mode == "score-prep":
            return self.scorePrepare(**kw)
        elif opt.mode == "score-batch":
            return self.scoreBatch(**kw)
        elif opt.mode == "combine-scores":
            return self.combineScores(**kw)
        else:
            raise ValueError("Unknown opt.mode value: %s" % (opt.mode,))


    def getSeqDb(self):
        opt = self.opt
        if self.seqDb is None:
            self.seqDb = SeqDbFasta.open(opt.seqDb) #"r"
        return self.seqDb


    def getImmPath(self,immId):
        return self.immStore.getImmPath(immId)

    def getScoreBatchPath(self,scoreBatchId):
        return self.store.getFilePath("%s%s" % (scoreBatchId,self.scoreSfx))
    
    def trainOne(self,**kw):
        """Train and save one IMM.
        Parameters are taken from self.opt
        @param immId Assign this ID to the IMM
        @param immSeqIds List of sequence ids from seqDb
        @param immMeta Meta data dict for immId
        """
        opt = self.opt
        immId = opt.immId
        immSeqIds = opt.immSeqIds
        immMeta = opt.immMeta
        seqDb = self.getSeqDb()
        immPath = self.getImmPath(immId)
        imm = Imm(path=immPath)
        try:
            inp = imm.train()
            seqDb.writeFastaBothStrands(ids=immSeqIds,out=inp,maxLen=opt.trainMaxLenSampModel)
            inp.close()
            imm.flush()
        except:
            # remove any unfinished ICM file if anything went wrong
            rmf(immPath)
            raise
        #@todo When making models for iterative binning+assembly,
        #immSeqIds can get long. Perhaps not save it here,
        #or make it a name of a separate file. This data is
        #currently used by benchmark code.
        immMeta.update(dict(seq_db_ids=immSeqIds))
        self.immStore.saveMetaDataById(immId,meta=immMeta)

    def trainMany(self,**kw):
        """Train many IMMs.
        Parameters are taken from self.opt
        @param immIdToSeqIds File name that contains a dict (immId->immSeqIds)
        """
        opt = self.opt
        #We do not generate opt.immIdToSeqIds here even when we can because
        #in that case it is difficult to make sure when we score that all
        #IMMs have been successfuly built.
        immIdToSeqIds = loadObj(opt.immIdToSeqIds)
        immIdToMeta = loadObj(opt.immIdToMeta)
        jobs = []
        for (immId,immSeqIds) in sorted(immIdToSeqIds.items()):
            immOpt = copy(opt)
            immOpt.mode = "train-one"
            immOpt.immId = immId
            immOpt.immSeqIds = immSeqIds
            immOpt.immMeta = immIdToMeta[immId]
            immApp = self.factory(opt=immOpt)
            jobs += immApp.run(**kw)
        #TODO: add combiner job that validates that all models have been built
        return jobs

    def scoreBatch(self,**kw):
        """Score with a batch of several IMM.
        Parameters are taken from self.opt
        @param immIds Score with these IMMs into these idScores (in-memory list of tuples
        (immId,idScore) - the models will be scored in the order supplied; the scores
        will be saved in the order of unique idScores supplied)
        @param inpSeq Name of the input multi-FASTA file or SeqDbFasta store to score
        @param outDir Directory name for output score files
        """
        opt = self.opt
        immIds = opt.immIds
        inpType = "file"
        inpSeq = opt.inpSeq
        print "DEBUG: scoreBatch: inpSeq={}".format(opt.inpSeq)
        try:
            if SeqDbFasta.isStore(inpSeq):
                inpSeq = SeqDbFasta.open(inpSeq,"r")
                inpType = "store"
                inpSeqDbIds = load_config_json(opt.inpSeqDbIds)
                assert inpSeqDbIds, "List of SeqDbFasta IDs for scoring is empty: {}".\
                        format(opt.inpSeqDbIds)

            outScoreBatchFile = self.getScoreBatchPath(opt.scoreBatchId)
            outScoreBatchFileWork = makeWorkFile(outScoreBatchFile)
            with closing(
                    openImmScores(
                        opt,fileName=outScoreBatchFileWork,mode="w",
                        idScore=unique(([rec[1] for rec in immIds]),stable=True)
                        )
                    ) as immScores:
                for immId,idScore in immIds:
                    imm = Imm(path=self.getImmPath(immId))
                    if inpType == "file":
                        scores = imm.score(inp=inpSeq)
                        imm.flush()
                    elif inpType == "store":
                        with closing(imm.score()) as inp:
                            inpSeq.writeToStreamByIds(ids=inpSeqDbIds,out=inp)
                        imm.flush()
                        #TODO: have parseScore return iter of recarrays
                        scores = imm.parseScores()
                    else:
                        raise ValueError(inpType)
                    immScores.appendScore(idScore=idScore,score=scores)
        finally:
            if inpType == "store":
                inpSeq.close()
        os.rename(outScoreBatchFileWork,outScoreBatchFile)

    def scorePrepare(self,**kw):
        """Prepare data once before all batches are scored.
        Parameters are taken from self.opt
        @param inpSeq Name of the input multi-FASTA file or SeqDbFasta store to score
        @param inpSeqDbIds This parameter will be a JSON
        file that will be populated here with all SeqDb IDs in inpSeqDbFilt
        unless that file already exists.
        """
        opt = self.opt
        if SeqDbFasta.isStore(opt.inpSeq):
            with closing(SeqDbFasta.open(opt.inpSeq,"r")) as inpSeq:
                if not os.path.exists(opt.inpSeqDbIds):
                    seqDbIds = inpSeq.getIdList()
                    save_config_json(seqDbIds,opt.inpSeqDbIds)
                else:
                    seqDbIds = load_config_json(opt.inpSeqDbIds)
                assert seqDbIds, \
                        "Input sequence store with sequences to score has no "+\
                        "partitions {}".format(opt.inpSeq)
                for (idSeqDb,lengths) in  inpSeq.seqLengthsMany(seqDbIds):
                    if len(lengths) > 0:
                        break
                else:
                    raise AssertionError("No scoring fragments in: {}"\
                            .format(opt.inpSeq))
    
    def scoreMany(self,**kw):
        """Score with many IMMs.
        Parameters are taken from self.opt
        @param immIds Path to list[(IMM ID to score with,idScore)] N->1 relation. 
        The idScore groups will be shuffled (for load-balancing) with 
        the original order of immIds preserved within groups, and then concatenated
        array will be split into equal batches of immIds. This shuffled order of idScores
        will become the final output order. Shuffling will be done, however, not randomly
        but with a hash function (by building a dict). This is done to make easier 
        concatenation of outputs for separate batches of input sequences by having the 
        order of idScore stable across invocations of this method.
        @param inpSeq Name of the input multi-FASTA file or SeqDbFasta store to score
        @param inpSeqDbIds If inpSeq is SeqDbFasta store, this parameter can be JSON
        file name with the list if SeqDb IDs to use for scoring. If undefined, it will
        be set to a file with all SeqDb IDs under cwd.
        @param nImmBatches Number of IMM batches (determines number of batch jobs)
        @param outDir Directory name for output score files
        @param outScoreComb name for output file with combined scores
        """
        opt = self.opt
        #create Prepare task
        prepOpt = copy(opt)
        #stay in the same cwd
        prepOpt.cwdHash = 0
        prepOpt.mode = "score-prep"
        immApp = self.factory(opt=prepOpt)
        jobs = immApp.run(**kw)
        kw = kw.copy()
        kw["depend"] = jobs
        
        #create batch scoring tasks
        makedir(opt.outDir)
        jobs = []
        immIds = loadObj(opt.immIds)
        rmf(opt.outScoreComb)
        #group by idScore and shuffle by hashing
        idScoreToImmId = defdict(list)
        for (immId,idScore) in immIds:
            idScoreToImmId[idScore].append(immId)
        #flatten back into array of tuples
        immIdsShf = list()
        for (idScore,immIdsScore) in idScoreToImmId.items():
            immIdsShf += [ (immId,idScore) for immId in immIdsScore ]
        #split with array_split. Some idScore will end up in different batches - the output
        #object will still merge them into one record at the end
        immIds = n.asarray(immIdsShf,dtype="O")
        scoreBatchIds = [] # accumulate batch ids to pass to combiner
        nImmBatches = opt.nImmBatches
        if nImmBatches < 0:
            nImmBatches = estimateNBatchesForScoring(
                    nModels = len(immIds),
                    inpSeq = opt.inpSeq,
                    inpSeqDbIds = opt.inpSeqDbIds
                    )
        batches = [ x for x in enumerate(n.array_split(immIds,min(nImmBatches,len(immIds)))) ]
        
        rmfMany([ self.getScoreBatchPath(scoreBatchId) for (scoreBatchId,immIdsBatch) in batches ])

        for (scoreBatchId,immIdsBatch) in batches:
            immOpt = copy(opt)
            #stay in the same cwd because self.getScoreBatchPath() depends on it
            immOpt.cwdHash = 0
            immOpt.mode = "score-batch"
            immOpt.immIds = immIdsBatch #now this is a sequence, not a file name
            immOpt.scoreBatchId = scoreBatchId
            immApp = self.factory(opt=immOpt)
            jobs += immApp.run(**kw)
            scoreBatchIds.append(scoreBatchId)

        #create combiner task
        coOpt = copy(opt)
        coOpt.mode = "combine-scores"
        coOpt.scoreBatchIds = scoreBatchIds
        #stay in the same cwd because self.getScoreBatchPath() depends on it
        coOpt.cwdHash = 0
        coApp = self.factory(opt=coOpt)
        kw = kw.copy()
        kw["depend"] = jobs
        jobs = coApp.run(**kw)
        return jobs

    def combineScores(self,**kw):
        """Combine scores as a final stage of scoreMany().
        Parameters are taken from self.opt
        @param immIds List of IMM IDs to score with
        @param inpSeq Name of the input multi-FASTA file or SeqDbFasta store that was 
        scored (to pull seq lengths from it here)
        @param inpSeqDbIds If inpSeq is SeqDbFasta store, this parameter must be JSON
        file name with the list if SeqDb IDs as was used for scoring
        @param outDir Directory name for output score files
        @param outScoreComb name for output file with combined scores
        """
        opt = self.opt
        immIds = sorted(loadObj(opt.immIds))
        outScoreCombWork = makeWorkFile(opt.outScoreComb)
        immScores = openImmScores(opt,fileName=outScoreCombWork,mode="w")
        outScoreBatchFiles = [ self.getScoreBatchPath(scoreBatchId) \
                for scoreBatchId in opt.scoreBatchIds ]
        immScores.catScores(fileNames=outScoreBatchFiles,
                idScoreSel=set((idScore for (idImm,idScore) in immIds)))
        if opt.isDef("inpSeqDbIds"):
            #input sequences were in SeqDbFasta store
            #we need to extract the lengths in the same order
            #that was used for scoring, that is in the order
            #defined by inpSeqDbIds
            inpSeqDbIds = load_config_json(opt.inpSeqDbIds)
            with closing(SeqDbFasta.open(opt.inpSeq,"r")) as inpSeq:
                immScores.setLenSamp( 
                        (
                            lengths for (idSeq,lengths) in  \
                                    inpSeq.seqLengthsMany(inpSeqDbIds) 
                        ),
                        sourceType = "iter_recarrays"
                    )
        else:
            lenSamp = fastaLengths(opt.inpSeq,exclSymb=self.degenSymb)
            immScores.setLenSamp(lenSamp,sourceType="recarray")
        immScores.close()
        os.rename(outScoreCombWork,opt.outScoreComb)
    

if __name__ == "__main__":
    #Allow to call this as script
    runAppAsScript(ImmApp)

