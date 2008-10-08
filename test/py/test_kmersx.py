from MGTX.kmersx import *

import numpy

kmerLen = 8

#seqStr = "aaaaaaccccccccccggggggggggggttttttttttttttt".upper()

seqStr = ''.join([
"GATCTTACCCTCAAATATTATTAATCTACGACTATAAAGCTAACAATCCTTAAAAAGCTTGTCAATTTTTACTCTAAATA",
"ATAAAATCATAATTAACCAAAAACAAACTCTAAGAAGGAGGAGGAAAAATGAGTAAAATGCGTATTGGTGTATTAACAGG",
"TGGAGGCGATTGCCCAGGTCTAAACCCAGCTATCCGTGGTATTGTCATGAGAGCATTAGATTATGGAGACGAAGTTATAG",
"GTTTGAAGTATGGATGGGCTGGTCTTCTTAAGGCAGATACTATGCCTTTATCCTTAGAAATGGTAGAAGATATTCTTGAA",
"ATCGGCGGAACAATTCTTGGAAGTTCTAGAACAAACCCATTCAAAAAAGAAGAAGATGTTCAAAAATGTGTTGAGAACTT",
"CAAAAAGTTAAACTTAGATGCCTTAATCGCCATAGGTGGAGAAGACACTCTAGGAGTTGCATCAAAATTTAGCAAACTTG",
"GTCTTCCAATGATCGGAGTTCCAAAAACTATTGATAAAGATTTAGAAGAAACTGACTATACTCTTGGATTTGACACTGCT",
"GTTGAAGTAGTGGTAGATGCAATTAAAAGACTTAGAGATACTGCAAGATCTCATGCAAGAGTTATCGTAGTAGAAATAAT",
"GGGAAGACATGCAGGATGGTTAGCTCTTTATGGTGGGCTTGCAGGAGGAGCAGATTATATCTTAATCCCTGAAGTAGAAC",
"CTAATCTTGAGGATCTTTACAATCACATAAGAAAACTATACGCAAGAGGAAGAAATCACGCAGTTGTAGCCATCGCTGAG",
"GGAGTACAACTACCAGGATTTACTTATCAAAAAGGACAAGAAGGAATGGTAGATGCCTTTGGTCACATTCGCTTAGGTGG",
"TGTAGGTAATGTACTAGCCGAAGAGATACAGAAGAACTTGGGAATTGAAACCAGAGCCGTAATCTTAAGCCACCTACAAA",
"GGGGAGGAAGTCCATCAATAAGAGATAGAATCATGGGGCTTCTCCTTGGTAAGAAGGCTGTAGACTTAGTACATGAAGGA"
])

seq = numpy.fromstring(seqStr,dtype="S1")

print seqStr

counter = KmerCounter(kmerLen,True)

nSeq = len(seq)

counts = numpy.zeros(nSeq,numpy.int32)
indices = numpy.zeros(nSeq,numpy.int64)

for it in range(10000):
    counter.process(seq)
    (size,total) = counter.counts(counts,indices)
    #isort = numpy.argsort(indices[:size])
    #ind = indices[isort]
    #cnt = counts[isort]

print size, total

print indices
print counts

counter.openOutput("test_kmersx.svm")
counter.process(seq)
counter.process(seq)
counter.frequencesWriteSvmSparseTxt(10)
counter.process(seq)
counter.frequencesWriteSvmSparseTxt(100)
counter.closeOutput()
