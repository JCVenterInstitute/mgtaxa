--ALTER TABLE seq
--ADD INDEX src(taxid,src_db,kind,project),
--add index taxid(taxid),
--add index src_db(src_db),
--add index kind(kind),
--add index project(project),
--add index acc(acc);
--analyze table seq;

DROP TABLE taxa_src_1;
CREATE TABLE taxa_src_1
        AS
        (SELECT taxid        ,
                src_db       ,
                kind         ,
                project      ,
                0            AS priority,
                COUNT(*)     AS cnt     ,
                SUM(seq_len) AS seq_len
        FROM    seq
        GROUP BY taxid ,
                src_db ,
                kind   ,
                project)
        WITH DATA;

DROP TABLE taxa_src;
CREATE TABLE taxa_src
        AS
        (SELECT * from taxa_src_1)
        ORDER BY taxid ,
                src_db ,
                kind   ,
                project
        WITH DATA;

DROP TABLE taxa_src_1;

ALTER TABLE taxa_src 
ADD id INTEGER auto_increment PRIMARY KEY;

--ALTER TABLE taxa_src
--ADD INDEX taxid(taxid)
--ADD INDEX src_db(src_db)
--ADD INDEX kind(kind)
--ADD INDEX project(project);

DELETE
FROM    taxa_src
WHERE   kind = 'AC';


--select a.kind,a.src_db,(project<>'') as has_proj, max(seq_len) as max_seq_len, left(b.descr,100) as descr from taxa_src a, refseq_acc b where a.kind = b.prefix group by a.src_db,a.kind,has_proj order by src_db,kind,has_proj;
-- Fix the 'project' field
-- alter table seq disable keys;
-- update seq set project = left(acc,4) where kind = '' and acc regexp '^([[:alpha:]]{2}_)*[[:alpha:]]{4}[[:digit:]]+.*';
-- update seq set project = substr(acc,4,4) where kind <> '' and acc regexp '^([[:alpha:]]{2}_)*[[:alpha:]]{4}[[:digit:]]+.*';
-- alter table seq enable keys;
--select a.* from taxa_src a where exists (select 1 from taxa_src b where a.taxid = b.taxid and a.kind <> '' and b.kind = '' and a.seq_len < b.seq_len and a.src_db in ('g','o') and b.src_db not in ('n')) order by a.taxid,a.seq_len;
--select a.*,b.* from taxa_src a, taxa_src b where a.taxid = b.taxid and a.kind <> '' and b.kind = '' and a.seq_len < b.seq_len and a.src_db in ('g','o') and b.src_db not in ('n')) order by a.taxid,a.seq_len;
---- No AC_
---- Hopefully annotation filtered contaminants, so it is preferred over WGS even if shorter
---- kind > 100000 => kind
---- max(kind <> '', wgs)
--create temporary table taxa_state
--(
--index taxid(taxid), index taxa_src_id(taxa_src_id)
--)
--engine memory
--(
--select distinct taxid, 0 as taxa_src_id from taxa_src
--);
--update taxa_src set priority = -1 where kind = 'AC';
--select distinct a.*,b.* from taxa_src a, taxa_src b where a.priority = 0 and b.priority = 0 and a.kind = 'NC' and b.kind <> 'NC'
--and a.seq_len < b.seq_len and a.taxid = b.taxid and a.src_db in ('o','g','w','h') and b.src_db in ('o','g','w','h');
--select * from taxa_src a where priority = 0 and kind = 'NC' and seq_len >= any (select seq_len from taxa_src b where a.taxid = b.taxid and src_db in ('o','g','w','h'));
--update taxa_src a set priority = 1 where priority = 0 and kind = 'NC' and seq_len >= any (select seq_len from taxa_src b where a.taxid = b.taxid);
--update taxa_src a set priority = 2 where priority = 0 and taxid not in  (select distinct taxid from taxa_src b where priority > 0) and kind in ('');

DROP TABLE wgs_src_1;
CREATE TABLE wgs_src_1
        AS
        (SELECT *
        FROM    taxa_src
        WHERE   project <> ''
            AND kind    <> ''
        )
        WITH DATA;
INSERT
INTO    wgs_src_1
SELECT  a.*
FROM    taxa_src a
WHERE   a.project   <> ''
    AND a.taxid NOT IN
        (SELECT taxid
        FROM    wgs_src_1
        );
DROP TABLE wgs_src_2;
CREATE TABLE wgs_src_2
        AS
        (SELECT a.*
        FROM    wgs_src_1 a
        WHERE   a.seq_len >= 
                (SELECT max(b.seq_len)
                FROM    wgs_src_1 b
                WHERE   a.taxid = b.taxid
                )
        )
        WITH DATA;
DROP TABLE wgs_src_1;
DROP TABLE wgs_src_3;
CREATE TABLE wgs_src_3
        AS
        (SELECT a.*
        FROM    wgs_src_2 a
        WHERE   a.id >= 
                (SELECT max(b.id)
                FROM    wgs_src_2 b
                WHERE   a.taxid = b.taxid
                )
        )
        WITH DATA;
DROP TABLE wgs_src_2;
DROP TABLE wgs_src_nr;
CREATE TABLE wgs_src_nr
        AS
        (SELECT *
        FROM    wgs_src_3
        )
        WITH DATA;
DROP TABLE nc_src_1;
CREATE TABLE nc_src_1
        AS
        (SELECT a.*
        FROM    taxa_src a
        WHERE   a.kind        = 'NC'
            AND a.seq_len * 2 > 
                (SELECT max(b.seq_len)
                FROM    wgs_src_nr b
                WHERE   a.taxid = b.taxid
                )
        )
        WITH DATA;
DROP TABLE htg_over_nc_src_1;
CREATE TABLE htg_over_nc_src_1
        AS
        (SELECT a.*
        FROM    taxa_src a,
                nc_src_1 b
        WHERE   a.src_db     = 'h'
            AND a.kind      <> 'NC'
            AND a.taxid      = b.taxid
            AND a.seq_len    > b.seq_len * 5
            AND b.seq_len    < 500000
            AND a.taxid NOT IN
                (SELECT taxid
                FROM    wgs_src_nr
                )
        )
        WITH DATA;
DROP TABLE nc_src_2;
CREATE TABLE nc_src_2
        AS
        (SELECT *
        FROM    nc_src_1
        WHERE   taxid NOT IN
                (SELECT taxid
                FROM    htg_over_nc_src_1
                )
        )
        WITH DATA;
DROP TABLE nc_src_3;
CREATE TABLE nc_src_3
        AS
        (SELECT a.*
        FROM    nc_src_2 a
        WHERE   a.id >= 
                (SELECT max(b.id)
                FROM    nc_src_2 b
                WHERE   a.taxid = b.taxid
                )
        )
        WITH DATA;
DROP TABLE nc_src;
CREATE TABLE nc_src
        AS
        (SELECT a.*,'nc' as stage
        FROM    nc_src_3 a
        )
        WITH DATA;
DROP TABLE wgs_src;
CREATE TABLE wgs_src
        AS
        (SELECT a.*,'wg' as stage
        FROM    wgs_src_nr a
        WHERE   taxid NOT IN
                (SELECT taxid
                FROM    nc_src
                )
        )
        WITH DATA;
DROP TABLE htg_src_1;
CREATE TABLE htg_src_1
        AS
        (SELECT *
        FROM    taxa_src
        WHERE   ( src_db      = 'h'
             OR kind       <> '' ) 
            AND (taxid NOT IN
                (SELECT taxid
                FROM    nc_src
                )
            AND taxid NOT IN
                (SELECT taxid
                FROM    wgs_src
                )
                )
        )
        WITH DATA;
DROP TABLE htg_src;
CREATE TABLE htg_src
        AS
        (SELECT a.*,'ht' as stage
        FROM    htg_src_1 a
        )
        WITH DATA;
--'union' is not allowed in 'create table name (select ....)'
DROP TABLE gen_src;
CREATE TABLE gen_src
        AS
        (SELECT *
        FROM    nc_src
        )
        WITH DATA;
INSERT
INTO    gen_src
SELECT  *
FROM    wgs_src

UNION

SELECT  *
FROM    htg_src;
CREATE INDEX taxid ON gen_src
        (
        taxid
        );
DROP TABLE nt_src;
CREATE TABLE nt_src
        AS
        (SELECT a.*,'nt' as stage
        FROM    taxa_src a
        WHERE   taxid NOT IN
                (SELECT taxid
                FROM    gen_src
                )
        )
        WITH DATA;

DROP TABLE all_src_1;

CREATE TABLE all_src_1
        AS
        (SELECT a.*,'g' as src_type
        FROM    gen_src a
        )
        WITH DATA;

INSERT
INTO    all_src_1
SELECT  a.*,'o' as src_type
FROM    nt_src a;

drop table all_src;
create table all_src
AS
(select a.*,b.cat,c.divid,c.rank 
from all_src_1 a 
left join taxa_cat b on a.taxid = b.taxid,
left join taxa_node c on a.taxid = c.taxid
)
WITH DATA;

--ALTER TABLE all_src 
--ADD INDEX taxid(taxid), 
--ADD INDEX src_db(src_db), 
--ADD INDEX kind(kind), 
--ADD INDEX project(project), 
--ADD INDEX cat(cat),
--ADD INDEX divid(divid), 
--ADD INDEX rank(rank), 

ALTER TABLE all_src 
ADD PRIMARY KEY id(id);

--reporting:
--have a single taxid entry per source database
drop table src_db_stat;
create table src_db_stat
        AS
        (SELECT src_db,
                taxid ,
                COUNT(*) AS cnt
        FROM    all_src
        GROUP BY src_db,
                taxid
        )
        WITH DATA;

SELECT  src_db,
        count(*)
FROM src_db_stat
GROUP BY src_db;

drop table taxa_stat;
create table taxa_stat
        AS
        (SELECT src_type,
                stage,
                taxid,
                cat,
                COUNT(*) AS cnt
        FROM    all_src
        GROUP BY src_type, stage,
                taxid,
                cat
        )
        WITH DATA;

select stage,count(*)
from taxa_stat
group by stage;

select stage,cat,count(*)
from taxa_stat
group by stage, cat;

select src_type,cat,count(*)
from taxa_stat
group by src_type, cat;

SELECT  COUNT(*)
FROM    all_src
WHERE   kind = 'NC';

--human must be NC only
SELECT  *
FROM    all_src
WHERE   taxid = 9606;

--final list of sequences

--ALTER TABLE seq
--ADD INDEX src(taxid,src_db,kind,project);

--SQLDIAL(mySQL)
--ALTER TABLE all_src 
--ADD INDEX src(taxid,src_db,kind,project);

drop table seq_sel;
create table seq_sel
AS
(
select a.*,
b.cat,
b.stage,
b.src_type,
SUBSTRING_INDEX( a.acc , '.', 1 ) as acc_no_ver,
b.divid,
b.rank
from seq a, all_src b
where 
a.taxid = b.taxid and
a.src_db = b.src_db and
a.kind = b.kind and
a.project = b.project and
a.taxid <> 0
)
WITH DATA;

--SQLDIAL(mySQL)
--ALTER TABLE seq_sel
--ADD INDEX taxid(taxid)  ,
--ADD INDEX src_db(src_db),
--ADD INDEX kind(kind)    ,
--ADD INDEX project(project),
--ADD INDEX cat(cat),
--ADD INDEX stage(stage),
--ADD INDEX src_type(src_type),
--ADD INDEX gi(gi),
--ADD INDEX acc(acc),
--ADD INDEX acc_no_ver(acc_no_ver),
--ADD INDEX divid(divid),
--ADD INDEX rank(rank),
ALTER TABLE seq_sel
ADD PRIMARY KEY iid(iid);


--Proved to be essential in MySQL for efficient planning of queries
--SQLDIAL(MySQL): analyze table seq_sel;

--Create table for Entrez viral and phage accessions and load them from a file
--create table vir_entrez (acc varchar(20) primary key,sub char(1));
--load data infile "/home/atovtchi/work/phyla/entrez/vis.acc" into table vir_entrez;
--update vir_entrez set sub = 'v';
--load data infile "/home/atovtchi/work/phyla/entrez/phg.acc" into table vir_entrez;
--update vir_entrez set sub = 'p' where sub is NULL;
--alter table viz_entrez add index sub(sub);
--select * from vir_entrez where acc not in (select acc_no_ver from seq_sel);
--select * from vir_entrez a, seq_sel b where a.acc = b.acc_no_ver and b.cat <> 'V';

--45202 is taxid for "unidentified plasmids" node under "other" - cloning vectors, synthetic constructs, plasmids
--and other that we do not need
-- select * from seq_sel where taxid = 45202 limit 10;
--delete from seq_sel where taxid = 45202;
 
 select divid, count(*) from seq_sel group by divid;
 select rank, count(*) from seq_sel group by rank;
 
--Backup all records from seq_sel that are to be discarded in case we want to analyze them later
drop table seq_sel_del;
create table seq_sel_del like seq_sel;
ALTER TABLE seq_sel_del DISABLE KEYS;
insert into seq_sel_del
--divid Synthetic, Unassigned and Environmental will be dropped,
--as well as with no longer valid taxonomy IDs
select * from seq_sel
where taxid is NULL or divid is NULL or cat is NULL
or divid in (7,8,11);
ALTER TABLE seq_sel_del ENABLE KEYS;

--SQLDIAL(MySQL) analyze table seq_sel_del;

--drop records earlier selected for deletion
delete from seq_sel where iid in (select iid from seq_sel_del);
--SQLDIAL(MySQL) analyze table seq_sel;

--save gis only into a file to be used as gi list for NCBI alias db
SELECT gi INTO OUTFILE '/home/atovtchi/scratch/mgtdata/phyla_sel.gi'
  FIELDS TERMINATED BY ' '
  LINES TERMINATED BY '\n'
  FROM seq_sel
  order by taxid,iid;
--save all importand fields for selected seq records into a flat file to be merged with 
--fasta sequence data extracted from blast databases through just created gi list
--the order must match the preceding 'select' for gis
--Full csv format will have something like OPTIONALLY ENCLOSED BY '"'
SELECT gi,taxid,src_db,kind,project,cat,stage,src_type,iid,seq_len,divid,rank 
  INTO OUTFILE '/home/atovtchi/scratch/mgtdata/phyla_sel.csv'
  FIELDS TERMINATED BY ' '
  LINES TERMINATED BY '\n'
  FROM seq_sel
  order by taxid,iid;
  
