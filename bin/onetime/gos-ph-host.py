from MGT.Proj.PhHostGosApp import *
from MGT.ImmScalingApp import *
from MGT.ImmClassifierApp import *

jobs = []

topWorkDir = os.environ["GOSII_WORK"]

topPredDir = pjoin(topWorkDir,"ph-pred")
#topPredDir = pjoin(topWorkDir,"ph-pred-random-inp")
topRndSeqDir = pjoin(topWorkDir,"scaff-rnd")

stage = "gos"

if stage == "ref":

    opt = Struct()
    opt.runMode = "inproc" #"inproc"
    refname = "refseq"
    #refname = "gos-bac"
    opt.immDb = pjoin(topWorkDir,"icm-%s" % refname)
    opt.workDir = pjoin(topWorkDir,"ph-gos-bac")
    #opt.predSeq = pjoin(topRndSeqDir,"query.5K.fna")
    #opt.predSeq = "/usr/local/projects/GOSII/shannon/Indian_Ocean_Viral/asm_combined_454_large/454LargeContigs.fna"
    opt.predSeq = pjoin(topWorkDir,"scaff-gos-vir","asm_combined_454_large.5K.fna")
    #opt.predSeq = pjoin(opt.workDir,"asm_combined_454_large.5K.rnd.fna")
    opt.predOutDir = pjoin(topPredDir,"asm_combined_454_large")
    #opt.predOutDir = pjoin(topWorkDir,"icm-%s-scale-score" % refname)
    opt.outDir = opt.predOutDir
    opt.rndScoreComb = pjoin(topWorkDir,"icm-%s-scale-score" % refname,"combined.score.pkl.gz")
    opt.nImmBatches = 200
    opt.predMinLenSamp = 5000

    for mode in ("proc-scores",):
        opt.mode = mode #"predict" "proc-scores" #"proc-scores-phymm" #"perf" #"proc-scores"
        app = ImmClassifierApp(opt=opt)
        jobs = app.run(depend=jobs)
    sys.exit(0)
    opt.cwd = opt.workDir
    opt.outScaleDir = pjoin(topWorkDir,"icm-%s-scale" % refname)
    opt.outScoreDir = pjoin(topWorkDir,"icm-%s-scale-score" % refname)
    
    for mode in ("score",): #generate score
        opt.mode = mode
        app = ImmScalingApp(opt=opt)
        jobs = app.run(depend=jobs)


elif stage == "gos":

    opt = Struct()
    opt.runMode = "inproc" #"inproc" #"batchDep"
    modes = ["proc-scores"] #"stats-pred" "export-pred" "proc-scores" "score-imms-gos"] #"train-imms-gos"] #"make-custom-seq"]
    jobs = []
    for mode in modes:
        opt.mode = mode
        app = PhHostGosApp(opt=opt)
        jobs = app.run(depend=jobs)

else:
    raise ValueError("Unknown stage value: %s" % stage)

