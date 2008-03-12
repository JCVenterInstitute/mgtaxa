from MGT.Common import *

def dbClose(dbObj):
    print "Running 'atexit()' handler"
    dbObj.close()

class DbSQL:
    
    def __init__(self):
        atexit.register(dbClose, dbObj=self)

    def ddlIgnoreErr(self,*l,**kw):
        curs = self.cursor()
        try:
            curs.execute(*l,**kw)
        except StandardError, msg:
            print msg
            pass
        curs.close()
        
    def ddl(self,*l,**kw):
        curs = self.cursor()
        curs.execute(*l,**kw)
        curs.close()
        
    def execute(self,*l,**kw):
        curs = self.cursor()
        curs.execute(*l,**kw)
        return curs

    def executemany(self,*l,**kw):
        curs = self.cursor()
        curs.executemany(*l,**kw)
        curs.close()
 
    def dropTable(self,name):
        self.ddl("drop table if exists " + name)

    def dropIndex(self,name,table):
        self.ddl("drop index  if exists %s on %s" % (name,table))

    def connection(self):
        return self.con
    
    def cursor(self):
        return self.con.cursor()
    
    def commit(self):
        if hasattr(self,'con'):
            self.con.commit()

    def close(self):
        pass
   
class DbSQLLite(DbSQL):
    
    def __init__(self,dbpath,strType=str,dryRun=False):
        from pysqlite2 import dbapi2 as dbmod
        self.dbmod = dbmod
        DbSQL.__init__(self)
        self.strType = strType
        self.dbpath = dbpath
        self.dryRun = dryRun
        self.con = self.dbmod.connect(self.dbpath)
        self.con.text_factory = self.strType


    def close(self):
        self.commit()
        if hasattr(self,'con'):
            self.con.close()


class DbSQLMy(DbSQL):
    
    def __init__(self,dryRun=False):
        import MySQLdb as dbmod
        self.dbmod = dbmod
        DbSQL.__init__(self)        
        #self.dbmod.server_init(("phyla","--defaults-file=my.cnf"),('server',))
        self.con = self.dbmod.connect(unix_socket="/tmp/atovtchi.mysql.sock",
                                      host="localhost",
                                      db="phyla",
                                      user="root",
                                      passwd="OrangeN0",
                                      read_default_file="my.cnf",
                                      read_default_group="client")


    def close(self):
        self.commit()
        if hasattr(self,'con'):
            self.con.close()
        #self.dbmod.server_end()


class DbSQLMonet(DbSQL):
    
#sql>CREATE USER "root" WITH PASSWORD 'OrangeN0' NAME 'Main User' SCHEMA "sys";
#sql>CREATE SCHEMA "mgtaxa" AUTHORIZATION "root";
#sql>ALTER USER "root" SET SCHEMA "mgtaxa";
	
    def __init__(self,dryRun=False):
        import MonetSQLdb as dbmod
        self.dbmod = dbmod
        DbSQL.__init__(self)        
        #self.dbmod.server_init(("phyla","--defaults-file=my.cnf"),('server',))
        self.con = self.dbmod.connect(host = 'localhost',
            dbname = 'mgtaxa',
            user = 'root',
            password = 'OrangeN0', 
            lang = 'sql')

    def close(self):
        self.commit()
        if hasattr(self,'con'):
            self.con.close()
        #self.dbmod.server_end()


def createDbSQL():
    #db = DbSQLLite("/export/atovtchi/test_seq.db")
    db = DbSQLMonet()
    return db


class BulkInserter:
    
    def __init__(self,cursor,sql,bufLen):
        self.cursor = cursor
        self.bufLen = bufLen
        self.sql = sql
        self.buf = []
        
    def __call__(self,record):
        self.buf.append(record)
        if len(self.buf) == self.bufLen:
            self.flush()
            
    def flush(self):
        if len(self.buf) > 0:
            self.cursor.executemany(self.sql,self.buf)
            self.buf = []




class DbSeqSource(PhyOptions):
    """Database of sequence source for training the classiffier"""
    
    def __init__(self,dbSql):
        
        PhyOptions.__init__(self)
        
        self.dbSql = dbSql
        self.ncbiDbs =  (
                         Struct(id='g',db='refseq_genomic'),
                         Struct(id='o',db='other_genomic'),
                         Struct(id='n',db='nt'),
                         Struct(id='h',db='htgs'),
                         Struct(id='w',db='wgs')
                         )


    def makeBlastAlias(self,idList=None,dbNames=None):
        from glob import glob
        from datetime import datetime
        from textwrap import dedent
        if dbNames is None:
            dbNames = [ db.db for db in self.ncbiDbs ]
        directDbRefs = False
        #comment out GILIST field in alias file if idList is None
        if idList is None:
            comGILIST = '#'
        else:
            comGILIST = ''
        dbNameAlias = self.srcDbNameAlias
        idListBin = dbNameAlias+'.gil'
        aliasStr = dedent("""\
        #
        # Alias file created %s
        #
        #
        TITLE Custom Unified DB for Phyla
        #
        DBLIST %%s
        #
        %sGILIST %s
        #
        #OIDLIST
        #
        """ % (datetime.today().ctime(),comGILIST,idListBin))
        cwd = os.getcwd()
        try:
            os.chdir(self.blastDataDir)
            if directDbRefs:
                chunks = []
                for rec in dbNames:
                    chunks += sorted(list(set(
                                    ( y.group(1) for y in  
                                      (re.match('('+rec.db+'\.[0-9]+)\..*',x) 
                                       for x in glob(rec.db+'.*')) 
                                    if y is not None )
                                    )))
            else:
                chunks = dbNames
            strToFile(aliasStr % ' '.join(chunks),dbNameAlias+'.nal')
        finally:
            os.chdir(cwd)
        
    def mergeSelWithSeq(self,skipSeq=False):
        #from itertool import izip
        outFasta = gzip.open(self.selFastaFile,'w',compresslevel=4)
        inpDump = open(self.selDumpFile,'r')
        selGiFile = os.path.abspath(self.selGiFile)
        fldsDump = "gi,taxid,src_db,kind,project,cat,stage,src_type,iid,seq_len,divid,rank".split(',')
        pipe = Popen(("fastacmd -i %s -d %s" % (selGiFile,self.srcDbNameAlias)).split(), 
                     cwd=self.blastDataDir, env=os.environ, bufsize=2**16, stdout=PIPE, close_fds=True).stdout
        #inpFasta = readFastaRecords(pipe,readSeq=True)
        FGI_SKIP  = 0x01
        FGI_WRITE = 0x02
        FGI_MISM  = 0x04
        giSeen = {}
        iRec = 0
        skip = True
        mismatchRun = 0 # how many gi mismatches in a row
        for line in pipe:
            try:
                if line.startswith(">"):
                    skip = False
                    #header line can be:
                    #>gi|23455713|ref|NC_004301.1| Enterobacteria phage FI, complete genome >gi|15183|emb|X07489.1| Bacteriophage SP genomic RNA
                    headers = line.split('>')
                    gi2 = -1
                    if len(headers) > 2:
                        hdr2 = headers[2]
                        if hdr2.startswith('gi|'):
                            gi2 = int(hdr2.split('|',2)[1])
                            if not giSeen.has_key(gi2):
                                giSeen[gi2] = 0
                    (gifld,gi,accfld,acc,txt) = line[1:].split('|',4)
                    assert gifld == 'gi'
                    gi = int(gi)
                    valsDump = inpDump.readline().rstrip('\n').split(' ') #empty string fields will be ok
                    giDump = int(valsDump[0])
                    taxidDump = int(valsDump[1])
                    try:
                        lineage = self.taxaTree.getNode(taxidDump).lineageRanksStr()
                    except KeyError:
                        lineage = 'NULL'
                        print "Warning: Lineage not found for taxid %s" % (taxidDump,)
                    if giDump == gi:
                        line = ">gi|%s|%s|%s|" % (gi,accfld,acc) + \
                            ''.join(["%s:%s " % (fld,val) for (fld,val) in zip(fldsDump[1:],valsDump[1:])]) + \
                            "lineage:%s " % (lineage,) + \
                            txt
                        if gi2 > 0:
                            giSeen[gi2] |= FGI_WRITE
                        mismatchRun = 0                            
                    elif giDump == gi2:
                        giSeen[giDump] |= FGI_SKIP
                        skip = True
                        mismatchRun = 0
                    else:
                        if mismatchRun >= 10:
                            raise ValueError("Mismatch between FASTA and SQl DUMP input streams:" + \
                                "fastaTitle = %s valsDump = %s" % (line,' '.join(valsDump)))
                        else:
                            if not giSeen.has_key(giDump):
                                giSeen[giDump] = 0
                            giSeen[giDump] |= (FGI_SKIP | FGI_MISM)
                            skip = True
                            mismatchRun += 1
                            print "GI mismatch for ", giDump
                    if iRec % 10000 == 0:
                        print "Done %s records" % (iRec,)
                    iRec += 1
                elif skipSeq:
                    skip = True
                if not skip:
                    outFasta.write(line)
            except:
                print "Exception with input line: ", line
                pipe.close()
                raise
        pipe.close()
        inpDump.close()
        outFasta.close()
        print 'giSeen = \n', sorted(giSeen.items())
        print 'len(giSeen) = ',len(giSeen)
        for (gi,val) in sorted(giSeen.items()):
            if val & FGI_SKIP and not val & FGI_WRITE:
                print "%s never written %s" % (gi,val)
            if val & FGI_MISM:
                print "%s mistamtch %s" % (gi,val)


    def loadSeq(self):
        self.loadGiTaxPickled()
        self.createTableSeq()
        self.loadSeqNCBI(self.ncbiDbs[0])
        #self.loadSeqNCBI(self.ncbiDbs[1])
        #self.loadSeqNCBI(self.ncbiDbs[2])
        #self.loadSeqNCBI(self.ncbiDbs[3])
        #self.loadSeqNCBI(self.ncbiDbs[4])
        #self.dbSql.ddl("create index taxid on seq(taxid)")
    
    def createTableSeq(self):
        self.dbSql.dropIndex("taxid","seq")
        self.dbSql.dropTable("seq")
        self.dbSql.execute(
        """
        create table seq
        (
        iid integer auto_increment primary key ,
        gi bigint,
        taxid integer,
        src_db varchar(1),
        project varchar(4),
        seq_len bigint,
        acc varchar(20),
        kind varchar(2),
        seq_hdr varchar(%s)
        )
        engine myisam
        """ % (self.fastaHdrSqlLen,))
        
    def loadSeqNCBI(self,db):
        pipe = Popen(("fastacmd -D 1 -d " + db.db).split(), cwd=self.blastDataDir, env=os.environ, bufsize=2**16, stdout=PIPE, close_fds=True).stdout
        inp = readFastaRecords(pipe,readSeq=False)
        curs = self.dbSql.cursor()
        iRec = 0
        bufLen = 500
        sql = """
        insert into seq
        (gi, taxid, src_db, project, seq_len, acc, kind, seq_hdr)
        values
        (%s,%s,%s,%s,%s,%s,%s,%s)
        """
        inserter = BulkInserter(cursor=curs,sql=sql,bufLen=bufLen)
        for rec in inp:
            (gifld,gi,accfld,acc,txt) = rec.title.split('|',4)
            assert gifld == 'gi'
            gi = int(gi)
            try:
                taxid = self.gi2taxa[gi]
            except KeyError:
                print "Taxid not found for gi: "+gi
                taxid = 0
            #Accession number formats are described here:
            #http://www.ncbi.nlm.nih.gov/Sequin/acc.html
            #WGS id might be 'AAAA00000000' or 'NZ_AAAA00000000', both cases seen in wgs db
            kind = ''
            acc_sfx = acc
            if acc_sfx[2] == '_':
                kind = acc_sfx[:2]
                acc_sfx = acc_sfx[3:]
            project = ''
            if acc_sfx[:4].isalpha() and acc_sfx[5].isdigit():
                project = acc_sfx[:4]
            values = (gi,taxid,db.id,project,rec.seqLen(),acc,kind,rec.title[:self.fastaHdrSqlLen])
            #values = [ str(x) for x in values ]
            inserter(values)            
            if iRec % 10000 == 0:
                print rec.title, taxid, iRec
            iRec += 1
        inserter.flush()
        curs.close()

    def loadRefseqAcc(self):
        self.dbSql.dropTable('refseq_acc')
        self.dbSql.ddl("""\
        create table refseq_acc
        (prefix varchar(2), acc varchar(40), molecule varchar(10), method varchar(15), descr varchar(400), index prefix(prefix))
        engine myisam
        """)
        self.dbSql.executemany("""\
        insert into refseq_acc
        (prefix,acc,molecule,method,descr)
        values
        (%s,%s,%s,%s,%s)
        """,refseqAccFormat)
        
    def loadTaxCategories(self):
        self.dbSql.dropTable('taxa_cat')
        self.dbSql.ddl("""\
        create table taxa_cat
        (cat char(1), taxid_ancestor integer, taxid integer)
        engine myisam
        """)
        inp = open(self.taxaCatFile,'r')
        curs = self.dbSql.cursor()
        iRec = 0
        bufLen = 5000
        sql = """\
        insert into taxa_cat
        (cat,taxid_ancestor,taxid)
        values
        (%s,%s,%s)
        """
        inserter = BulkInserter(cursor=curs,sql=sql,bufLen=bufLen)
        for rec in inp:
            inserter(rec.split())
        inserter.flush()
        curs.close()
        self.dbSql.ddl("""\
        alter table taxa_cat  
        ADD PRIMARY KEY taxid(taxid), 
        add index cat(cat), 
        add index taxid_ancestor(taxid_ancestor)
        """)
        inp.close()

    def loadTaxNodes(self):
        self.dbSql.dropTable('taxa_node')
        self.dbSql.ddl("""\
        create table taxa_node
        (
        taxid integer,
        partaxid integer,
        rank varchar(20),
        embl_code  char(2),
        divid  integer,
        inh_div  bool,
        gcode_id integer,
        inh_gc  bool,
        mgcode_id integer,
        inhmgc  bool,
        gbhidden bool,
        hidsubtree bool,
        comments  varchar(40)
        )
        engine myisam
        """)
        inp = open(self.taxaNodesFile,'r')
        curs = self.dbSql.cursor()
        iRec = 0
        bufLen = 5000
        sql = """\
        insert into taxa_node
        (
        taxid,
        partaxid,
        rank,
        embl_code,
        divid,
        inh_div,
        gcode_id,
        inh_gc,
        mgcode_id,
        inhmgc,
        gbhidden,
        hidsubtree,
        comments
        ) 
        values
        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        inserter = BulkInserter(cursor=curs,sql=sql,bufLen=bufLen)
        for rec in inp:
            inserter(rec.split('\t|\t'))
        inserter.flush()
        curs.close()
        #Get rid of spaces in 'rank' field to simplify export of data later on
        self.dbSql.execute("update taxa_node set rank = replace(rank,' ','_')").close()
        self.dbSql.ddl("""\
        alter table taxa_node
        ADD PRIMARY KEY taxid(taxid), 
        add index partaxid(partaxid), 
        add index divid(divid)
        """)
        inp.close()


    def loadTaxNodesMem(self):
        self.taxaTree = TaxaTree(ncbiDumpFile=self.taxaNodesFile)
        #self.taxaTree.write(sys.stdout)

        
    def loadGiTaxSql(self):
        self.dbSql.dropTable("gi_taxa")
        self.dbSql.execute(
        """
        create table gi_taxa
        (
        gi bigint,
        taxid integer
        )
        engine myisam
        """)
        #self.dbSql.executemany("insert into gi_tax (gi,taxid) values (%s,%s)",[(1,2),(3,4)])
        #print "Test done"
        #self.dbSql.execute("insert into gi_tax (gi,taxid) values ('1','2')")
        inp = file(self.taxaGiFile,'r')
        iRow = 0
        bufLen = 100000
        sql = "insert into gi_taxa (gi,taxid) values (%s,%s)"
        curs = self.dbSql.cursor()        
        inserter = BulkInserter(cursor=curs,sql=sql,bufLen=bufLen)        
        print "Start insert"
        for record in inp:
            inserter(record.split())
            iRow += 1
            if iRow % 100000 == 0:
                print record,iRow
        inserter.flush()
        curs.close()
        inp.close()
        print "Start index build"
        self.dbSql.ddl("""\
        alter table gi_taxa  
        ADD PRIMARY KEY gi(gi), 
        add index taxid(taxid)
        """)
        

    def loadGiTaxBdb(self,inpFile):
        import anydbm, whichdb
        print whichdb.whichdb('/export/atovtchi/taxa.db')
        gi2taxa = anydbm.open('/export/atovtchi/taxa.db', 'c')
        inp = file(inpFile,'r')
        iRow = 0
        buff = {}
        for line in inp:
            (gi,taxid) = line.split()
            buff[gi] = taxid
            if iRow % 100000 == 0:
                print gi, taxid, iRow
                gi2taxa.update(buff)
                buff = {}
            iRow += 1
        inp.close()
        taxaCnt = {}
        for (gi,taxid) in gi2taxa.iteritems():
            taxaCnt[taxid] = taxaCnt.get(taxid,0) + 1
        print sorted(((cnt,taxid) for (taxid,cnt) in taxaCnt.iteritems()))

    def loadGiTaxNumpy(self):
        inp = openGzip(self.taxaGiFile,'r')
        gi2taxa = numpy.loadtxt(inp,dtype=numpy.int32)
        print gi2taxa.shape 
        dumpObj(gi2taxa,self.taxaPickled)

    def loadGiTaxPickled(self):
        inp = open(self.taxaPickled,'r')
        self.gi2taxa = load(inp)
        inp.close()


refseqAccFormat = \
(
('','','','','Undefined'),
('AC','AC_123456','Genomic','Mixed','Alternate complete genomic molecule. This prefix is used for records that are provided to reflect an alternate assembly or annotation. Primarily used for viral, prokaryotic records.'),
('AP','AP_123456','Protein','Mixed','Protein products; alternate protein record. This prefix is used for records that are provided to reflect an alternate assembly or annotation. The AP_ prefix was originally designated for bacterial proteins but this usage was changed.'),
('NC','NC_123456','Genomic','Mixed','Complete genomic molecules including genomes, chromosomes, organelles, plasmids.'),
('NG','NG_123456','Genomic','Mixed','Incomplete genomic region; supplied to support the NCBI genome annotation pipeline. Represents either non-transcribed pseudogenes, or larger regions representing a gene cluster that is difficult to annotate via automatic methods.'),
('NM','NM_123456 NM_123456789','mRNA','Mixed','Transcript products; mature messenger RNA (mRNA) transcripts.'),
('NP','NP_123456 NP_123456789','Protein','Mixed','Protein products; primarily full-length precursor products but may include some partial proteins and mature peptide products.'),
('NR','NR_123456','RNA','Mixed','Non-coding transcripts including structural RNAs, transcribed pseudogenes, and others.'),
('NT','NT_123456','Genomic','Automated','Intermediate genomic assemblies of BAC and/or Whole Genome Shotgun sequence data.'),
('NW','NW_123456 NW_123456789','Genomic','Automated','Intermediate genomic assemblies of BAC or Whole Genome Shotgun sequence data.'),
('NZ','NZ_ABCD12345678','Genomic','Automated','A collection of whole genome shotgun sequence data for a project. Accessions are not tracked between releases. The first four characters following the underscore (e.g. ''ABCD'') identifies a genome project.'),
('XM','XM_123456 XM_123456789','mRNA','Automated','Transcript products; model mRNA provided by a genome annotation process; sequence corresponds to the genomic contig.'),
('XP','XP_123456 XP_123456789','Protein','Automated','Protein products; model proteins provided by a genome annotation process; sequence corresponds to the genomic contig.'),
('XR','XR_123456','RNA','Automated','Transcript products; model non-coding transcripts provided by a genome annotation process; sequence corresponds to the genomic contig.'),
('YP','YP_123456 YP_123456789','Protein','Mixed','Protein products; no corresponding transcript record provided. Primarily used for bacterial, viral, and mitochondrial records.'),
('ZP','ZP_12345678','Protein','Automated','Protein products; annotated on NZ_ accessions (often via computational methods).')
)


    
