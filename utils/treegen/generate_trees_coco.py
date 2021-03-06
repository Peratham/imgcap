# Accepts a document of the form:
#
# <img_id> (tab) <img_description> (return)
#
# and then generates a tree of each img_description, tokenizing the
# words as it goes. it maintains a persistent word tokenization
# dictionary, called mapping, so that you can call it on an arbitrary
# number of files and there will be no word collisions. The parse trees
# are also maintained in a continuous file.
import os
import cPickle
from nltk.parse import stanford
from nltk.tree import Tree
from multiprocessing import Process, Queue
import time
import json

# You will need to customize this
PARSER_LOC = '/Users/ndufour/stanford-parser/stanford-parser.jar'
MODEL_LOC = '/Users/ndufour/stanford-parser/stanford-parser-3.5.2-models.jar'
PCFG_LOC = '/Users/ndufour/stanford-parser/stanford-parser-3.5.2-models/edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz'

#root = os.path.dirname(os.path.abspath(__file__))
root = '/Users/ndufour/Dropbox/Class/CS224D/project/imgcap/utils/treegen'

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

def get_map():
    # returns the current mapping
    if not os.path.exists(os.path.join(root, 'mapping')):
        return dict()
    else:
        f = open(os.path.join(root, 'mapping'),'r').read()
        mapping = dict()
        for i in f.split('\n'):
            if len(i):
                spl = i.split('\t')
                mapping[spl[0]] = int(spl[1])
        return mapping

def seen_ids():
    # returns a set of IDs tha thave already been seen by the parser
    if not os.path.exists(os.path.join(root, 'trees.txt')):
        return set()
    else:
        sid = set()
        f = open(os.path.join(root, 'trees.txt')).read().split('\n')
        for i in f:
            if not len(i):
                continue
            cid, _ = i.split('\t')
            sid.add(cid)
        return sid

mapping = get_map()
seen = seen_ids()

def init_parser():
    # initializes the parser
    os.environ['STANFORD_PARSER'] = PARSER_LOC
    os.environ['STANFORD_MODELS'] = MODEL_LOC
    parser = stanford.StanfordParser(model_path=PCFG_LOC)
    return parser

def gk(item):
    if not mapping.has_key(item):
        with open(os.path.join(root, 'mapping'),'a') as mapf:
            v = item
            k = len(mapping)
            mapping[v] = k
            mapf.write('%s\t%i\n'%(v,k))
    return mapping[item]

def worker(qIN, qOUT, workerN, nWorkers):
    # queue worker; instantiates its own stanford parse, then dequeues
    # sentences from qIN, parses them, adds them to qOUT.
    # format of each qIN item:
    # <id> <sentence> <num> <tot_num>
    print 'Initializing worker'
    parser = init_parser()
    for n,qr in enumerate(qIN):
        if (n%nWorkers)==workerN:
            cids, descs = qr
            print 'Worker %i starting parse chunk %i/%i...'%(workerN, n, len(qIN))
            parse = parser.raw_parse_sents(descs)
            print 'Worker %i parse chunk %i/%i complete...'%(workerN, n, len(qIN))
            nparse = [y.next() for y in parse]
            for cid, parse in zip(cids, nparse):
                qOUT.put([cid, str(parse)])

def get_str(tree):
    if type(tree)==unicode or type(tree)==str:
        return str(gk(tree))
    if len(tree) == 1:
        return get_str(tree[0])
    return '(' + ' '.join([get_str(x) for x in tree]) + ')'

def printTime(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%dh:%02dm:%02ds" % (h, m, s)

filename1 = '/Users/ndufour/Dropbox/Class/CS224D/project/imgcap/data/mscoco/captions_train2014.json'
filename2 = '/Users/ndufour/Dropbox/Class/CS224D/project/imgcap/data/mscoco/captions_val2014.json'

f = []
f1 = open(filename1, 'r').read()
f+= json.loads(f1)['annotations']
f1 = open(filename2, 'r').read()
f+= json.loads(f1)['annotations']

# okay, so instead it's going to work by chunking data into groups of
# 500 sentences

qIN = []
qOUT = Queue()
n_procs = 5
cids = seen_ids()
print 'Enqueuing sentences'
tot = 0
chunk_size = 500
cur_chunk_desc = []
cur_chunk_id = []
for n,line in enumerate(f):
    cid, descr = [line['image_id'].decode('utf-8'), line['caption'].decode('utf-8').lower()]
    if cid in cids:
        print 'Already seen %s'%(cid)
        continue
    cur_chunk_desc.append(descr)
    cur_chunk_id.append(cid)
    if len(cur_chunk_desc)==chunk_size:
        qIN.append([cur_chunk_id, cur_chunk_desc])
        cur_chunk_desc = []
        cur_chunk_id = []
    tot += 1
qIN.append([cur_chunk_id, cur_chunk_desc])
p = []

if __name__=='__main__':
    print 'starting'
    for i in range(n_procs):
        p.append(Process(target=worker, args=(qIN, qOUT, i, n_procs)))
    for pr in p:
        pr.start()
        time.sleep(0.5)
    curcnt = 0
    start = time.time()
    with open(os.path.join(root, 'trees.txt'),'a') as treefile:
        while curcnt != tot or not qOUT.empty():
            curcnt += 1
            cid, parse = qOUT.get()
            parse = Tree.fromstring(parse)
            treestr = get_str(parse)
            remtime = printTime((tot-(curcnt+1))*(time.time()-start)/(curcnt+1))
            if not curcnt % 500:
                print '(%i / %i) [rem: %s] %s %s'%(curcnt, tot, remtime, cid, treestr)
            treefile.write('%s\t%s\n'%(cid, treestr))
    for pr in p:
        pr.join()
    print 'All are joined'


