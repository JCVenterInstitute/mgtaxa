### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the MGTAXA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


"""Application for phage/host assignment"""

from MGT.PhageHostDb import *
from MGT.Taxa import *
from MGT.Svm import *
from MGT.App import *
from MGT.DirStore import *
import UUID
from MGT.SeqImportApp import *
from MGT.ImmClassifierApp import ImmClassifierApp
from MGT.ImmApp import *
from MGT.Sql import *
import csv

from MGT.GFF import GFF3Record, GFF3Attributes

class TaxaPred(Struct):
    """Class to represent taxonomic predictions - one taxid per sample"""
    pass

class GFF3RecordPhageHostAnnot(GFF3Record):
    """Represents one record (line) in GFF3 file with initialization specific for Phage-Host annotation."""

    annDtype = [
    ("id_pep","O"),       #> JCVI-pep-ID
    ("id_read",idDtype),  #> READ-ID
    ("strand_pep","i1"),  #> Strand of the ORF with respect to the read
    ("id_contig",idDtype),#> Contig-ID
    ("start_read","i4"),  #> Start coordinate of read on contig
    ("end_read","i4"),    #> End coordinate of read on contig
    ("strand_read","S1"), #> Orientation of read with respect to contig (C = complement, U = unknown (?))
    ("type_ann","S32"),   #> Annotation type (ALLGROUP_PEP; CDD_RPS; PFAM/TIGRFAM_HMM; FRAG_HMM;ACLAME_HMM)
    ("id_ann",idDtype),   #> Evidence-ID
    ("descr_ann","O"),    #> Evidence-description
    #Derived here:
    ("taxid_ann",taxidDtype),  #Annotation taxid, extracted from descr_ann where available
    ("descr_ann_short","S32"), #Short description extracted from descr_ann for presentation
    #The following fields are added in this method by joining with our assigned host taxonomy:
    ("taxid_host",taxidDtype), #Taxid of aasigned host
    ("len_contig","i4"),       #Length of contig
    ]
    
    def fromAnnotRec(self,feat,taxaTree):
        """Pull data from annotation record defined in PhageHostApp.compareWithProtAnnot()"""
        self.type = "protein_match"
        self.start = feat["start_read"]
        self.end = feat["end_read"]
        feat_strand = feat["strand_pep"] * (-1 if (feat["strand_read"] == 'C') else 1)
        self.strand = '+' if feat_strand > 0 else '-' if feat_strand < 0 else '.'
        # no attributes should be automatically carried forward from the previous values:
        self.attribs = GFF3Attributes()
        ats = self.attribs
        ret = [ self ]
        if feat["taxid_ann"] != 0:
            try:
                tn = taxaTree.getNode(feat["taxid_ann"])
                tn_name = tn.name
            except KeyError:
                print "DBG: taxid %s is not found in taxonomy tree" % feat["taxid_ann"]
                tn_name = ''
        else:
            tn_name = ''
        ats["ID"] = "%s_%s" % (feat["id_pep"],feat["id_ann"])
        ats["Name"] = ' '.join((tn_name,feat["id_ann"],feat["descr_ann_short"].strip()))
        if len(ats["Name"]) == 0:
            ats["Name"] = ats["ID"]
        return ret

class PhageHostApp(App):
    """App-derived class for phage-host assignment"""

    batchDepModes = ("predict","train")

    maxSeqIdLen = UUID.maxIdLen
    maxSeqPartIdLen = UUID.maxIdLen

    @classmethod
    def makeOptionParserArgs(klass):
        from optparse import make_option
        optChoicesMode = ("build-db-ph","sel-db-ph-pairs","shred-vir-test","predict","cmp-prot-annot","perf")
        option_list = [
            make_option("-m", "--mode",
            action="store", type="choice",choices=optChoicesMode,
            dest="mode",default="predict",help=("What to do, choice of %s, default is %%default" % (optChoicesMode,))),
            make_option(None, "--taxa-tree-pkl",
            action="store", type="string",dest="taxaTreePkl",help="Custom taxonomy tree saved in pickle format. If not set, standard NCBI tree is used."),
            make_option(None, "--db-gb-inp",
            action="store", type="string",dest="dbGbInp",help="Input viral GenBank file for phage-host DB construction"),
            optParseMakeOption_Path(None, "--db-ph",
            dest="dbPh",
            help="DB of known phage-  host pairs created and used here",
            default="ph"),
            make_option(None, "--db-seq",
            action="append", type="string",dest="dbSeqInp",help="Input DB (e.g. RefSeq) FASTA sequence files for both microbes "+\
                    "and viruses referenced by phage-host pairs DB. It can be a subset of superset of p-h DB."),
            optParseMakeOption_Path(None, "--db-ph-pairs",
            default="ph-pairs",dest="dbPhPairs",help="Stratified phage-host pairs from DB phage-host"),
            optParseMakeOption_Path(None, "--db-ph-pairs-seq-ids",
            default="ph-pairs-seq-ids",dest="dbPhPairsSeqIds",help="Sequence IDs for db-ph-pairs - "+\
                    "intermediate file used to pull all sequences from the original FASTA files into db-ph-pairs-seq"),
            optParseMakeOption_Path(None, "--db-ph-pairs-seq",
            default="ph-pairs-seq",dest="dbPhPairsSeq",help="Sequences for db-ph-pairs in our "+\
                    "internal format"),
            make_option(None, "--shred-size-vir-test",
            action="store", type="int",default=5000,dest="shredSizeVirTest",help="Shred DB viral samples into this size for testing"),
            make_option(None, "--db-imm",
            action="store", type="string",default="imm",dest="immDb",help="Path to a collection of IMMs"),
            make_option(None, "--pred-seq",
            action="store", type="string",dest="predSeq",help="Path to a FASTA file with sequences to classify"),
            make_option(None, "--annot-cont",
            action="store", type="string",dest="annotCont",help="Path to a file with protein annotations mapped to viral contigs"),
            make_option(None, "--pred-out-dir",
            action="store", type="string",default="results",dest="predOutDir",help="Output directory for classification results"),
            make_option(None, "--pred-out-taxa",
            action="store", type="string",dest="predOutTaxa",help="Output file with predicted taxa; default is pred-taxa inside "+\
                    "--pred-out-dir"),
            make_option(None, "--pred-min-len-samp",
            action="store", type="int",default=0,dest="predMinLenSamp",help="Min length of samples to consider for prediction"),
        ]
        return Struct(usage = "Build phage-host association database, classifiers, and perform training, validation and de novo classification.\n"+\
                "%prog [options]",option_list=option_list)

    
    @classmethod
    def parseCmdLinePost(klass,options,args,parser):
        opt = options
        globOpt = globals()["options"]
        refSeqDir = globOpt.refSeqDataDir
        opt.setIfUndef("dbGbInp",pjoin(refSeqDir,"viral.genomic.gbff.gz"))
        opt.setIfUndef("dbSeqInp",[ pjoin(refSeqDir,div+".genomic.fna.gz") for div in ("microbial","viral")])
        opt.setIfUndef("predOutTaxa",pjoin(opt.predOutDir,"pred-taxa"))
        opt.setIfUndef("predOutTaxaCsv",opt.predOutTaxa+".csv")
        opt.setIfUndef("predOutDbSqlite",opt.predOutTaxa+".sqlite")
        opt.setIfUndef("predOutStatsDir", pjoin(opt.predOutDir,"stats"))
        opt.setIfUndef("predOutStatsCsv", pjoin(opt.predOutStatsDir,"stats.csv"))
        opt.setIfUndef("predOutAnnot",pjoin(opt.predOutDir,"annot"))
        opt.setIfUndef("outScoreComb",klass._outScoreCombPath(opt))
        opt.setIfUndef("taxaTreePkl",None)
        opt.setIfUndef("rejectRanksHigher","order")
   

    def initWork(self,**kw):
        opt = self.opt
        self.taxaTree = None #will be lazy-loaded
        self.taxaLevels = None #will be lazy-loaded
        self.store = SampStore.open(path=self.opt.get("cwd",os.getcwd()))

    def doWork(self,**kw):
        opt = self.opt
        if opt.mode == "build-db-ph":
            return self.buildDbPhageHost(**kw)
        elif opt.mode == "sel-db-ph-pairs":
            return self.selectPhageHostPairs(**kw)
        elif opt.mode == "shred-vir-test":
            return self.shredVirTest(**kw)
        elif opt.mode == "predict":
            return self.predict(**kw)
        elif opt.mode == "proc-scores":
            return self.processImmScores(**kw)
        elif opt.mode == "proc-scores-phymm":
            return self.processPhymmScores(**kw)
        elif opt.mode == "perf":
            return self.performance(**kw)
        elif opt.mode == "cmp-prot-annot":
            return self.compareWithProtAnnot(**kw)
        else:
            raise ValueError("Unknown opt.mode value: %s" % (opt.mode,))

    def getTaxaTree(self):
        if self.taxaTree is None:
            self.taxaTree = loadTaxaTree(pklFile=self.opt.taxaTreePkl,allNames=True)
        return self.taxaTree

    def getTaxaLevels(self):
        if self.taxaLevels is None:
            #that assigns "level" and "idlevel" attributes to TaxaTree nodes
            self.taxaLevels = TaxaLevels(self.getTaxaTree())
        return self.taxaLevels

    def loadPhageHostDb(self):
        """Load and map Phage-Host DB into the taxaTree"""
        loadHosts(inpFile=self.store.getObjPath(self.opt.dbPh),taxaTree=self.getTaxaTree())
    
    def buildDbPhageHost(self,**kw):
        """Collect and save data about phage-host associations in RefSeq"""
        opt = self.opt
        taxaTree = self.getTaxaTree()
        vhParser = VirHostParser(taxaTree=taxaTree)
        vhParser.assignHostsAndSave(gbFile=opt.dbGbInp,outFile=self.store.getObjPath(opt.dbPh))

    def selectPhageHostPairs(self,**kw):
        """Pick pairs of phages and hosts from p-h DB stratified at a genus level"""
        opt = self.opt

        giToTaxa = loadGiTaxBin()
        taxaTree = self.getTaxaTree()


        #taxaTree.getRootNode().setIsUnderUnclass()

        mapFastaRecordsToTaxaTree(inSeqs=opt.dbSeqInp,taxaTree=taxaTree,giToTaxa=giToTaxa)
        self.loadPhageHostDb()

        seqPicker = PhageHostSeqPicker(taxaTree=taxaTree)
        seqPicker.pickSeqHosts()
        seqPicker.groupSeqHosts()
        seqPicker.printGroupSeqHosts()

        seqPicker.pickPairs(maxMicSpe=1,maxMicSeq=1,maxVir=1,maxVirSeq=1)
        seqPicker.checkPairs(giToTaxa=giToTaxa)

        dbPhPairsFile = self.store.getObjPath(opt.dbPhPairs)
        seqPicker.save(dbPhPairsFile)
        seqPicker.load(dbPhPairsFile)
        seqPicker.checkPairs(giToTaxa=giToTaxa)
        seqPicker.saveSeqIds(self.store.getObjPath(opt.dbPhPairsSeqIds))
        
        # import all selected FASTA sequences into internal format

        siOpt = Struct()
        siOpt.runMode = "inproc"
        siOpt.inSeq = opt.dbSeqInp
        siOpt.outFeat = opt.dbPhPairsSeq
        siOpt.inSeqIds = self.store.getObjPath(opt.dbPhPairsSeqIds)
        siOpt.inFormat = "ncbi"
        seqImpApp = SeqImportApp(opt=siOpt)
        seqImpApp.run()
    
        seqPicker = PhageHostSeqPicker(taxaTree=taxaTree)
        dbPhPairsFile = self.store.getObjPath(opt.dbPhPairs)
        seqPicker.load(dbPhPairsFile)
        for div in ("mic","vir","all"):
            self.store.saveIdLabs(seqPicker.makeIdLabsPicks(div=div),name="idlab."+div)

        self.exportVirSamples()

    def getVirSampStoreName(self):
        return "samp.v"
    
    def getVirSampStoreShredsName(self,shredSize):
        return "samp.v.%s" % shredSize

    def getVirSampStore(self):
        return self.store.subStore(self.getVirSampStoreName(),klass=SampStore)

    def getVirSampStoreShreds(self,shredSize):
        return self.getVirSampStore().subStore(self.getVirSampStoreShredsName(shredSize),klass=SampStore)
    
    def exportVirSamples(self):
        opt = self.opt
        sampStore = self.getVirSampStore()
        idLabs = self.store.loadIdLabs("idlab.vir")
        sampStore.fromPreProc(inpSamp=opt.dbPhPairsSeq,
                preProc=LoadSeqPreprocIdFilter(idToLab=idLabs.getIdToLab()))
        sampStore.makeIdLabs(idLabsSrc=idLabs,action="idfilt")
   
    def exportVirSamplesShreds(self,shredSize):
        opt = self.opt
        sampStore = self.getVirSampStore()
        shredStore = sampStore.makeShredStore(name=self.getVirSampStoreShredsName(shredSize),
                shredOpt=dict(sampLen=shredSize,sampNum=10)) #TMP
        shredStore.exportFasta(name="samp.fas",lineLen=1000)

    def shredVirTest(self,**kw):
        opt = self.opt
        self.exportVirSamplesShreds(shredSize=opt.shredSizeVirTest)

    @classmethod
    def _outScoreCombPath(klass,opt):
        o = Struct(outDir=opt.predOutDir,mode="predict")
        ImmClassifierApp.fillWithDefaultOptions(o)
        return o.outScoreComb

    def predict(self,**kw):
        """Predict host taxonomy for viral sequences.
        Parameters are taken from self.opt.
        @param predSeq Name of FASTA sequence file to classify
        @param immDb Path to directory with IMMs
        @param predOutDir Output directory for predictions
        """
        sopt = self.opt

        opt = copy(sopt)

        opt.mode = "predict"
        opt.inpSeq = sopt.predSeq
        opt.outDir = sopt.predOutDir
        immStore = ImmStore(opt.immDb)
        immIds = immStore.listImmIds()
        immIdsPath = pjoin(opt.outDir,"imm-ids.pkl")
        rmrf(opt.outDir)
        makedir(opt.outDir)
        dumpObj(immIds,immIdsPath)
        opt.immIds = immIdsPath
        #opt.predMode = "host"
        imm = ImmClassifierApp(opt=opt)
        jobs = imm.run(**kw)
        return jobs

    def _maskScoresNonSubtrees(self,taxaTree,immScores,posRoots):
        """Set to a negative infinity (numpy.NINF) all columns in score matrix that point to NOT subtrees of posRoots nodes.
        This is used to mask all scores pointing to other than bacteria or archaea when we are assigning hosts to viruses"""
        scores = immScores.scores
        idImms = immScores.idImm
        for (iCol,idImm) in enumerate(idImms):
            #assume here that idImm is a taxid
            node = taxaTree.getNode(idImm)
            if not (node.isSubnodeAny(posRoots) or node in posRoots):
                scores[:,iCol] = n.NINF

    def _maskScoresByRanks(self,taxaTree,immScores):
        """Set to a negative infinity (numpy.NINF) all columns in score matrix that point to nodes of ranks not in desired range.
        """
        opt = self.opt
        scores = immScores.scores
        idImms = immScores.idImm
        taxaTree = self.getTaxaTree()
        taxaLevels = self.getTaxaLevels()
        max_linn_levid = taxaLevels.getLevelId(opt.rejectRanksHigher)
        #min_linn_levid = max_linn_levid
        # Safe to set it to 0, because there is also at least superkingdom above 
        # min_linn_levid = taxaLevels.getLinnLevelIdRange()[0]
        min_linn_levid = 0
        # this still can exclude nodes that are above subtree that has no IMMs but 
        # below lowest max_lonn_levid (e.g. ref sequence attached directly to sub-species
        # that has strain nodes w/o sequence, and family node immediately above.
        # We need to assign is_leaf_imm attribute to taxaTree nodes to do it right.
        for (iCol,idImm) in enumerate(idImms):
            #assume here that idImm is a taxid
            node = taxaTree.getNode(idImm)
            # node.isLeaf() takes care of env sequences and ref strains under family
            if  (not node.isLeaf()) and \
                (not taxaLevels.isNodeInLinnLevelRange(node,min_linn_levid,max_linn_levid)):
                scores[:,iCol] = n.NINF
   
    def _taxaTopScores(self,taxaTree,immScores,topScoreN):
        """Get TaxaTree nodes of topScoreN scores for each sample.
        """
        scores = immScores.scores
        idImms = immScores.idImm
        taxaTree = self.getTaxaTree()
        taxaLevels = self.getTaxaLevels()
        #get indices of topScoreN largest scores in each row
        indScores = scores.argsort(axis=1)[:,-1:-topScoreN-1:-1]
        return idImms[indScores]

    def _getImmScores(self,reload=False):
        if not hasattr(self,"immScores") or reload:
            self.immScores = loadObj(self.opt.outScoreComb)
            self.immScores.idImm = n.asarray(self.immScores.idImm,dtype=int)
        return self.immScores


    rejTaxid = 0

    def _normalizeScores(self,immScores,immScoresRnd):
        sc = immScores
        scRand = immScoresRnd
        scoreRand = scRand.scores
        baseScoreRand = (scoreRand.T/scRand.lenSamp).T
        meanRand = baseScoreRand.mean(0)
        stdRand = baseScoreRand.std(0)
        normScoreRand = (baseScoreRand - meanRand)/stdRand
        baseScores = (sc.scores.T/sc.lenSamp).T
        assert n.all(scRand.lenSamp==scRand.lenSamp[0])
        ratLen = sc.lenSamp.astype(float)/scRand.lenSamp[0]
        # base score is an average of N random variables,
        # and therefore has a variance var(1-base)/N
        normScore = (baseScores - meanRand)/stdRand
        normScore = (normScore.T * ratLen**0.5).T
        #normScore = baseScores/meanRand
        #normScore = baseScores
        #pdb.set_trace()
        # we could also return dot(stdRand,ratLen**0.5) to give
        # avg base score std per given sample length by a given IMM on random
        # sequence, but the distribution on our random set is virtually normal,
        # and it is much to the left from the distribution of actual samples,
        # so there is no sense in using percentile cutoffs like 95%, which is
        # at about 1.645 z-score for standard normal distribution
        return normScore


    def processImmScores(self,**kw):
        """Process raw IMM scores to predict host taxonomy for viral sequences.
        Parameters are taken from self.opt.
        @param outScoreComb File with ImmScores object
        @param rndScoreComb File with ImmScores object for random query sequences
        @param predOutTaxa Output file with predicted taxa
        """
        import scipy.stats
        opt = self.opt
        sc = loadObj(opt.outScoreComb)
        #assume idImm are str(taxids):
        sc.idImm = n.asarray(sc.idImm,dtype=int)
        #scRnd = loadObj(opt.rndScoreComb)
        #sc.scores = self._normalizeScores(sc,scRnd)
        taxaTree = self.getTaxaTree()
        taxaLevels = self.getTaxaLevels()
        scores = sc.scores
        idImms = sc.idImm
        micRoots = tuple([ taxaTree.getNode(taxid) for taxid in micTaxids ])
        virRoot = taxaTree.getNode(virTaxid)
        #scVirRoot = scores[:,idImms == virTaxid][:,0]
        #scCellRoot = scores[:,idImms == cellTaxid][:,0]
        self._maskScoresNonSubtrees(taxaTree,immScores=sc,posRoots=micRoots)
        if opt.rejectRanksHigher is not "superkingdom":
            self._maskScoresByRanks(taxaTree,immScores=sc)
        topTaxids = self._taxaTopScores(taxaTree,immScores=sc,topScoreN=10)
        argmaxSc = scores.argmax(1)
        maxSc = scores.max(1)
        ## @todo in case of score ties, pick the lowest rank if it is a single entry
        predTaxids = idImms[argmaxSc]
        #predTaxids[maxSc<10] = self.rejTaxid
        # this will reject any sample that has top level viral score more
        # that top level cellular org score, on the assumption that easily
        # assignbale viruses should be closer to cellular orgs than to other
        # viruses.
        # Result: removed 90 out of 250 samples, with no change in specificity.
        #predTaxids[scVirRoot>scCellRoot] = self.rejTaxid
        # this excluded 10 out of 430, no change in specificity
        #predTaxids[scVirRoot>=maxSc] = self.rejTaxid
        
        # This not the same as _maskScoresByRanks() above (because this
        # will actually assign a reject label.
        if opt.rejectRanksHigher is not "superkingdom":
            max_linn_levid = taxaLevels.getLevelId(opt.rejectRanksHigher)
            min_linn_levid = taxaLevels.getLinnLevelIdRange()[0]
            # Reject predictions to clades outside of certain clade level range,
            # as well as to any viral node
            # This rejected 36 out of 450 and resulted in 2% improvement in specificity
            for i in xrange(len(predTaxids)):
                if not predTaxids[i] == self.rejTaxid:
                    predNode = taxaTree.getNode(predTaxids[i])
                    if predNode.isUnder(virRoot):
                        predTaxids[i] = self.rejTaxid
                    # we need to protect leaf nodes because we place environmental scaffolds
                    # as no_rank under bacteria->environmental
                    elif not (predNode.isLeaf() or taxaLevels.isNodeInLinnLevelRange(predNode,
                            min_linn_levid,max_linn_levid)):
                        predTaxids[i] = self.rejTaxid

        pred = TaxaPred(idSamp=sc.idSamp,predTaxid=predTaxids,topTaxid=topTaxids,lenSamp=sc.lenSamp)
        dumpObj(pred,opt.predOutTaxa)
        self._exportPredictions(taxaPred=pred)
        self._statsPred()
        #todo: "root" tax level; matrix of predhost idlevel's; batch imm.score() jobs; score hist;

    def _exportPredictions(self,taxaPred):
        opt = self.opt    
        taxaTree = self.getTaxaTree()
        taxaLevels = self.getTaxaLevels()
        levNames = taxaLevels.getLevelNames("ascend")
        out = openCompressed(opt.predOutTaxaCsv,"w")
        flds = ["id","len","taxid","name","rank"]
        for lev in levNames:
            flds += ["taxid_"+lev,"name_"+lev]
        w = csv.DictWriter(out, fieldnames=flds, restval='null',dialect='excel-tab')
        w.writerow(dict([(fld,fld) for fld in flds]))
        for idS,taxid,lenS in it.izip(taxaPred.idSamp,taxaPred.predTaxid,taxaPred.lenSamp):
            if lenS < opt.predMinLenSamp:
                continue
            row = dict(id=idS,len=lenS,taxid=taxid)
            if taxid != self.rejTaxid:
                node = taxaTree.getNode(taxid)
                row["name"] = node.name
                row["rank"] = node.linn_level
                lin = taxaLevels.lineage(node,withUnclass=False)
                for ln in lin:
                    row["name_"+ln.level] = ln.name
                    row["taxid_"+ln.level] = ln.id
            w.writerow(row)
        out.close()

        db = DbSqlLite(dbpath=opt.predOutDbSqlite)
        db.createTableFromCsv(name="scaff_pred",
                csvFile=opt.predOutTaxaCsv,
                hasHeader=True,
                indices={"names":("id","taxid","name",)})
        db.close()

    def _statsPred(self,**kw):
        """Create aggregate tables and csv files to show various relationships between predictions"""
        opt = self.opt
        db = DbSqlLite(dbpath=opt.predOutDbSqlite)
        rmrf(opt.predOutStatsDir)
        makedir(opt.predOutStatsDir)
        outCsv = openCompressed(opt.predOutStatsCsv,'w')
        sqlAsComment = True
        sqlpar = dict(lenMin = 5000)
        sql = """select name,count(*) as cnt from scaff_pred group by name order by cnt desc"""
        comment = "Count of assignments grouped by reference name"
        db.exportAsCsv(sql,outCsv,comment=comment,sqlAsComment=sqlAsComment,epilog="\n")
        sql = """select name_species,count(*) as cnt from scaff_pred group by name_species order by cnt desc"""
        comment = "Count of assignments grouped by reference species name"
        db.exportAsCsv(sql,outCsv,comment=comment,sqlAsComment=sqlAsComment,epilog="\n")
        sql = """select name_genus,count(*) as cnt from scaff_pred group by name_genus order by cnt desc"""
        comment = "Count of assignments grouped by reference genus name"
        db.exportAsCsv(sql,outCsv,comment=comment,sqlAsComment=sqlAsComment,epilog="\n")
        sql = """select name_family,count(*) as cnt from scaff_pred group by name_family order by cnt desc"""
        comment = "Count of assignments grouped by reference family name"
        db.exportAsCsv(sql,outCsv,comment=comment,sqlAsComment=sqlAsComment)
        outCsv.close()
        db.close()

    def _loadBlastAnnotEvalues(self,hitKeys):
        """A quick fix to add e-values to peptide annotation table loaded by compareWithProtAnnot"""
        #The lines of interest to us are like these:
        #JCVI_PEP_metagenomic.orf.1120383692912.1        ALLGROUP_PEP    rf|YP_912045.1 ... <e-value>
        evalueCacheFile = "hit_e_val.pkl"
        if not os.path.exists(evalueCacheFile):
            inpFiles = [
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS108viral-4F-01-677_FRDNTY201.db.evidence",
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS112viral-4F-01-661_FRDLTJ301.db.evidence",
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS117viral-4F-01-677_FRHLGZN01.db.evidence",
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS110viral-4F-01-650_FRHLGZN01.db.evidence",
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS117viral-4F-01-664_FRI4PDL01.db.evidence",
                "/usr/local/projects/GOSII/hlorenzi/IO/INTERACTIONS/annotation/GS122viral-4F-01-677_FRJHH4T01.db.evidence"
                ]
            recs = []
            for inpFile in inpFiles:
                print "DEBUG: processing %s, collected %s records" % (inpFile,len(recs))
                inp = openCompressed(inpFile,'r')
                #skip header
                inp.next()
                recs += [ (w[0].strip(),w[2].strip(),float(w[-1])) for w in \
                        ( line.strip().split('\t') for line in inp ) \
                        if len(w) >= 3 and \
                        w[1].strip() == "ALLGROUP_PEP" and 
                        (w[0].strip(),w[2].strip()) in hitKeys ]
            #m = defdict(list)
            #for rec in recs:
            #    m[(rec[0],rec[1])].append(rec[2])
            dumpObj(recs,evalueCacheFile)
        else:
            print "DEBUG: loading e-values from cache dump file"
            recs = loadObj(evalueCacheFile)
        m = dict( ( ((rec[0],rec[1]),rec[2]) for rec in recs ) )
        # assertion fails with difference 20K out of 200K; multiple records for query_seq,db_seq
        #assert len(m) == len(recs)
        return m


    def compareWithProtAnnot(self,**kw):
        """Compare our predicted host taxonomy with protein level annotations.
        Annotations are loaded from a tab delimited file that maps hits from
        various database searches onto predicted peptides, which are mapped
        onto reads, which are in turn mapped onto phage contigs/scaffolds that we
        used as input to predict the bacterial hosts.
        The expectation is that we might see e.g. BLAST hits to phages with a known
        host range, or to the hosts themselves.
        Parameters are taken from self.opt.
        @param contAnnot Input file with protein annotations projected onto viral contigs
        @param predOutTaxa Output file with predicted taxa
        """
        #Fields of the input annotation file and the assigned dtype:
        annDtype = [
        ("id_pep","O"),       #> JCVI-pep-ID
        ("id_read",idDtype),  #> READ-ID
        ("strand_pep","i1"),  #> Strand of the ORF with respect to the read
        ("id_contig",idDtype),#> Contig-ID
        ("start_read","i4"),  #> Start coordinate of read on contig
        ("end_read","i4"),    #> End coordinate of read on contig
        ("strand_read","S1"), #> Orientation of read with respect to contig (C = complement, U = unknown (?))
        ("type_ann","S32"),   #> Annotation type (ALLGROUP_PEP; CDD_RPS; PFAM/TIGRFAM_HMM; FRAG_HMM;ACLAME_HMM)
        ("id_ann",idDtype),   #> Evidence-ID
        ("descr_ann","O"),    #> Evidence-description
        #Derived here:
        ("taxid_ann",taxidDtype),  #Annotation taxid, extracted from descr_ann where available
        ("descr_ann_short","S80"), #Short description extracted from descr_ann for presentation
        #Loaded from extra file:
        #E-value of ALLGROUP_PEP BLAST hit
        ("e_val","f4"),
        #The following fields are added in this method by joining with our assigned host taxonomy:
        ("taxid_host",taxidDtype), #Taxid of aasigned host
        ("len_contig","i4"),       #Length of contig
        ]
        # default e-value, to set when not defined in extra file
        defEval = 1e-2
        #mnemonics for field indices in annotation file
        i_CONT = 3
        opt = self.opt
        pred = loadObj(opt.predOutTaxa)
        contToPred = indexTuples(it.izip(pred.idSamp,pred.predTaxid,pred.lenSamp))
        inpAnn = openCompressed(opt.annotCont,"r")
        annot = []
        for words in (line.split('\t') for line in inpAnn):
            cont = words[i_CONT].strip()
            if cont in contToPred:
                pred = contToPred[cont]
                if pred[2] >= opt.predMinLenSamp:
                    annot.append(tuple((w.strip() for w in words)) + (0,'',defEval) + pred[1:])
            #if len(annot) >= 100:
            #    break
        annot = n.asarray(annot,dtype=annDtype)
        _to_sc_id_pep = numpyToScalarFunc(annot[0]["id_pep"])
        _to_sc_id_ann = numpyToScalarFunc(annot[0]["id_ann"])
        _hit_key = lambda rec: (_to_sc_id_pep(rec["id_pep"]),_to_sc_id_ann(rec["id_ann"]))
        hitKeys = set( ( _hit_key(rec) for rec in annot ) )
        mEval = self._loadBlastAnnotEvalues(hitKeys = hitKeys)
        for rec in annot:
            if rec["type_ann"] == "ALLGROUP_PEP":
                try:
                    rec["e_val"] = mEval[_hit_key(rec)]
                except KeyError:
                    print "DEBUG: %s not found in e-val map" % (rec,)
        #there are some negative start positions in the data - clip them
        annot["start_read"] = n.maximum(annot["start_read"],0)
        annot["end_read"] = n.minimum(annot["end_read"],annot["len_contig"])

        #there are reverted coords in input data - swap them
        inv = (annot["start_read"] >= annot["end_read"])
        start_read = n.select([inv],[annot["end_read"]],default=annot["start_read"])
        end_read = n.select([inv],[annot["start_read"]],default=annot["end_read"])
        annot["start_read"] = start_read
        annot["end_read"] = end_read
        
        for rec in annot:
            if rec["type_ann"] == "ALLGROUP_PEP":
                #re.findall returns list of group tuples
                name_and_tax = re.findall(".*\|\w+\W(.*)\Wtaxon:\b*([0-9]+)\W",rec["descr_ann"])
                if len(name_and_tax):
                    rec["taxid_ann"] = int(name_and_tax[0][1])
                    rec["descr_ann_short"] = name_and_tax[0][0]
                else:
                    print "DEBUG: taxon field expected but not found: %s" % rec["descr_ann"]
                    rec["descr_ann_short"] = rec["descr_ann"]
            else:
                #id_ann can be repeated up to twice in different case at the start of descr_ann
                #@todo not correct for FRAG_HMM - apparently it is parsed wrongly when tab splitting
                descr_ann_short = re.findall(".*%s\W+(.*)" % re.escape(rec["id_ann"]),rec["descr_ann"],re.IGNORECASE)
                if len(descr_ann_short):
                    rec["descr_ann_short"] = descr_ann_short[0]
                else:
                    rec["descr_ann_short"] = rec["descr_ann"]

        #self.plotContigAnnotGff(annRecs=annot,outGraphFileRoot="tmp_")
        annotTable = annot
        annot = groupRecArray(annot,"id_contig")
        #pdb.set_trace()
        taxaTree = self.getTaxaTree()
        outGraphDir  = pjoin(opt.predOutAnnot,"gd")
        makedir(outGraphDir)
        makedir(pjoin(outGraphDir,"long"))
        makedir(pjoin(outGraphDir,"func"))
        makedir(pjoin(outGraphDir,"clade"))
        def _out_graph_root(kind):
            return pjoin(outGraphDir,kind,"ann")
        #pdb.set_trace()
        for id_contig,annRecs in annot.items():
            annById = groupRecArray(annRecs,"id_ann")
            # take only one (first) annotation with a given id_ann
            annRecs = recFromRecords([ v[0] for v in annById.values() ])
            self.plotContigAnnotGff(annRecs=annRecs,
                    outGraphFileRoot=_out_graph_root("long"))
            self.plotContigAnnotGff(annRecs=annRecs[annRecs["type_ann"] != "ALLGROUP_PEP"],
                    outGraphFileRoot=_out_graph_root("func"))
            #group by annot higher-order clade (genus) and take one (first) record for each
            #ATTENTION: this will leave just one per-clade annotation per contig. Better would
            #be to group annotations by coordinate first, but we do not have exact enough coords
            #at this time.
            annRecsSp = []
            for rec in annRecs:
                taxid_ann = rec["taxid_ann"]
                if taxid_ann != 0:
                    try:
                        nodeAnn = taxaTree.getNode(taxid_ann)
                        nodeAnnSp = nodeAnn.findLeftRankInLineage(ranks=("genus","family","order"))
                        if nodeAnnSp is not None:
                            annRecsSp.append((nodeAnnSp.name,rec))
                    except KeyError:
                        print "DEBUG: taxid not found in taxonomy tree"
            annRecsSp = groupPairs(annRecsSp)
            annRecsSp = recFromRecords([ v[0] for v in annRecsSp.values() ],dtype=annRecs.dtype)
            self.plotContigAnnotGff(annRecs=annRecsSp,
                    outGraphFileRoot=_out_graph_root("clade"))

    def plotContigAnnotGff(self,annRecs,outGraphFileRoot,gdFormat="pdf"):
        """Generate GFF files and graphics based on protein annotation for viral contigs.
        @param gdFormat file type for genomic digrams, one of "pdf","png","svg" 
        (svg output in genometools (v.1.3.5) incorrectly clips a lot on the right side of the diagram)"""

        from MGT.GFF import GFF3Record, GFF3Header
        from MGT.GFFTools import GFF3Graphics
        #If annRecs is empty, many things downstream do not make sense
        if len(annRecs) == 0:
            return
        taxaTree = self.getTaxaTree()
        annRec1 = annRecs[0]
        outFileRt = outGraphFileRoot+(".%s.%s"%\
                (taxaTree.getNode(annRec1["taxid_host"]).name.replace(" ","_").replace("/","_"),\
                annRec1["id_contig"]))
        gffFile = outFileRt + ".gff3"
        out = open(gffFile,"w")
        out.write(str(GFF3Header()))
        orec = GFF3RecordPhageHostAnnot(seqid=annRec1["id_contig"])
        for feat in annRecs:
            for o in orec.fromAnnotRec(feat,taxaTree=taxaTree):
                out.write(str(o))
        out.close()
        grFile = outFileRt + ".%s" % (gdFormat,)
        gr = GFF3Graphics(outFormat=gdFormat,width=max(annRec1["len_contig"]/10,800))
        try:
            gr(gffFile,grFile)
        except CalledProcessError, msg:
            print "Creating genome diagram from GFF3 file failed: %s" % (msg,)

    def _idSampToPickedHostNode(self,idSamp,idToLab,taxaTree,virToHost):
        return n.vectorize(lambda id_samp: virToHost[taxaTree.getNode(int(idToLab[id_samp]))][0],otypes=["O"])(idSamp)

    def performance(self,**kw):
        """Evaluate the performance of predicting host taxonomy on the DB of known pairs.
        Parameters are taken from self.opt.
        @param predOutTaxa File with predicted taxa
        @param perfOutTaxa Output file with performance metrics
        @param predIdLab IdLabels file for the samples
        """
        opt = self.opt
        taxaTree = self.getTaxaTree()
        taxaTree.setMaxSubtreeRank()
        taxaLevels = self.getTaxaLevels()
        pr = loadObj(opt.predOutTaxa)
        idLab = loadObj(opt.predIdLab)
        idSamp = pr.idSamp
        predTaxids = pr.predTaxid
        idToLab = idLab.getIdToLab()
        virToHost = self.getVirToHostPicked()
        testHostNodes = self._idSampToPickedHostNode(idSamp=idSamp,idToLab=idToLab,taxaTree=taxaTree,virToHost=virToHost)
        
        
        lcs_lev = []
        lcs_idlev = []
        rejCnt = 0
        for predTaxid,idS,testHostNode in it.izip(predTaxids,idSamp,testHostNodes):
            if predTaxid == self.rejTaxid:
                rejCnt += 1
                continue
            predHostNode = taxaTree.getNode(predTaxid)
            virNode = taxaTree.getNode(int(idToLab[idS]))            
            lcsNode = testHostNode.lcsNode(predHostNode)
            lcs_lev.append(lcsNode.linn_level)
            lcs_idlev.append(taxaLevels.getLevelId(lcsNode.linn_level))
            print "lcsPredTest: ",lcsNode.linn_level,lcsNode.rank_max,lcsNode.name,"  ****  ",\
                    "predHost: ",predHostNode.name, predHostNode.rank_max,"  ****  ",\
                    "testHost: ",testHostNode.name,"  ****  ",\
                    "testVir: ",virNode.name
        print binCount(lcs_lev,format="list")
        lcs_ilev_cnt = binCount(lcs_idlev,format="list")
        lcs_lc = n.asarray([ (taxaLevels.getLevel(x[0]),x[1]) for x in lcs_ilev_cnt ],dtype=[("lev","O"),("cnt",int)])
        lcs_lc_linn = lcs_lc[lcs_lc["lev"] != "no_rank"]
        lcs_lc_linn = lcs_lc.copy()
        lcs_lc_linn[:-1] = lcs_lc[lcs_lc["lev"] != "no_rank"]
        lcs_lc_linn[-1:] = lcs_lc[lcs_lc["lev"] == "no_rank"]
        lcs_lc_cum = lcs_lc_linn.copy()
        lcs_lc_cum["cnt"] = lcs_lc_linn["cnt"].cumsum()
        print "Cumulative counts of correctly predicted hosts up to each level"
        print lcs_lc_cum
        lcs_lc_cum_rt = lcs_lc_cum.copy()
        lcs_lc_cum_rt["cnt"] = lcs_lc_cum["cnt"].astype(float)/lcs_lc_cum["cnt"][-1]*100
        print "Cumulative ratios of correctly predicted hosts up to each level (accuracy)"
        print lcs_lc_cum_rt
        print "Rejected: %s" % (rejCnt,)
        pdb.set_trace()

        topPredHostNodes = taxaTree.getNodes(pr.topTaxid)
        fmt = lambda node: "%s %s" % (node.linn_level,node.name)
        for testHostNode,predHostNodes in it.izip(testHostNodes,topPredHostNodes):
            lcs = testHostNode.lcsNodeMany(predHostNodes[:3])
            for (i,node) in enumerate(testHostNode.lineage()):
                print "  "*i,fmt(node),"XXX" if node is lcs else ""
            print "***"
            print "\n".join([(fmt(node)+" <> "+fmt(node.lcsNode(testHostNode))) for node in predHostNodes])
            print "\nxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"

    def getVirToHostPicked(self):
        """Return {virNode->host} map from a DB of picked vir-host pairs"""
        opt = self.opt
        taxaTree = self.getTaxaTree()
        seqPicker = PhageHostSeqPicker(taxaTree=taxaTree)
        dbPhPairsFile = self.store.getObjPath(opt.dbPhPairs)
        seqPicker.load(dbPhPairsFile)
        return seqPicker.seqVirHostPicks()

    def processPhymmScores(self,**kw):
        """Load Phymm predictions to use as a reference implementation.
        Parameters are taken from self.opt.
        @param outPhymm File with Phymm output
        @param predOutTaxa Output file with predicted taxa
        """
        opt = self.opt
        taxaTree = self.getTaxaTree()
        idSamp = []
        predTaxids = []
        inp = openCompressed(opt.outPhymm,'r')
        inp.next()
        for line in inp:
            fields = [ x.strip() for x in line.split('\t') ]
            id = fields[0].split('|')[0]
            #Phymm obfuscates original names below genus
            predNameGen = fields[3]
            predNode = taxaTree.searchName(predNameGen)
            if len(predNode):
                predNode = predNode[0]
                idSamp.append(id)
                predTaxids.append(predNode.id)
            else:
                print "No TaxaTree node found for name %s" % (predNameGen,)
        pred = TaxaPred(idSamp=n.asarray(idSamp,dtype=idDtype),pred=predTaxids)
        dumpObj(pred,opt.predOutTaxa)
        inp.close()
            
        

    def predictOld(self):
        opt = self.opt
        groupRanks = ("order","family","genus","subgenus","species")
        taxaTree = self.getTaxaTree()
        taxaTree.setMaxSubtreeRank()
        seqPicker = PhageHostSeqPicker(taxaTree=taxaTree)
        dbPhPairsFile = self.store.getObjPath(opt.dbPhPairs)
        seqPicker.load(dbPhPairsFile)
        virToHost = seqPicker.seqVirHostPicks()
        groupRanks = []
        inp = open("/usr/local/projects/GOSII/atovtchi/phymm/results.01.phymm____ph_samp_v_samp_v_400_samp_fas.txt",'r')
        inp.next()
        for line in inp:
            try:
                fields = line.strip().split('\t')
                taxid = int(float(fields[0].split('|')[1]))
                node = taxaTree.getNode(taxid)
                fields[0] = node.name
                predNameGen = fields[3]
                predNode = taxaTree.searchName(predNameGen)
                if len(predNode):
                    predNode = predNode[0]
                    hostNode = virToHost[node][0]
                    groupNode = hostNode.lcsNode(predNode)
                    #groupNode = hostNode.findLeftRankInLineage(groupRanks)
                    if groupNode:
                        groupName = groupNode.name
                        groupRank = groupNode.rank_max
                    else:
                        groupName = "None"
                        groupRank = "no_rank"
                    score = float(fields[2])
                    if score >= - 500:
                        print '\t|\t'.join([groupRank,groupName]+fields)
                        groupRanks.append(groupRank)
            except BaseException, msg:
                print "Exception caught for this line, skipping: %s \t %s" % (msg,line)
        inp.close()
        print binCount(groupRanks,format="list")

class VirHostClassifierScr:

    def __init__(self,virHostsFile=None):
        taxaTree = loadTaxaTreeNew()
        self.taxaTree = taxaTree
        self.micNodes = [ taxaTree.getNode(id) for id in micTaxids ]
        self.virNode = taxaTree.getNode(virTaxid)
        if virHostsFile is not None:
            self.loadVirHosts(virHostsFile)

    def loadVirHosts(self,fileName):
        phost = PhageHostSeqPicker(taxaTree=self.taxaTree)
        phost.load(fileName)
        self.phost = phost
        self.virHosts = phost.seqVirHosts()

    def splitFeatFileIntoVirHost(self,inpFiles,outName):
        data = loadSeqsMany(inpFiles)
        ids = set(data["id"])
        idToNode = {}
        for id in ids:
            idToNode[id] = self.getNCBINode(id)
        virNode = self.virNode
        isVir = n.asarray([ idToNode[id].isSubnode(virNode) for id in data["id"] ],dtype=bool)
        dataVir = data[isVir]
        dataMic = data[isVir!=True]
        labRenum = setLabelsFromIds(dataMic)
        micIdToLab = labRenum.toNew()
        virHostPicks = self.phost.seqVirHostPicks()
        idHostNoSamp = set()
        for rec in dataVir:
            idHost = "%s" % virHostPicks[idToNode[rec["id"]]][0].id
            try:
                rec["label"] = micIdToLab[idHost]
            except KeyError:
                idHostNoSamp.add(idHost)
                rec["label"] = 0
        if len(idHostNoSamp) > 0:
            print "Some hosts have no samples: %s" % (sorted(idHostNoSamp),)
        saveSeqs(dataVir,outName+".v.svm")
        saveSeqs(dataMic,outName+".m.svm")
        dumpObj(labRenum,outName+".labren")

    def getNCBINode(self,idSamp):
        return self.taxaTree.getNode(int(idSamp))



def run_splitFeatFileIntoVirHost():
    vhc = VirHostClassifierScr(virHostsFile="../viralHostsPick.pkl")
    vhc.splitFeatFileIntoVirHost(inpFiles=["all.svm"],outName="all")


if __name__ == "__main__":
    #Allow to call this as script
    runAppAsScript(PhageHostApp)
