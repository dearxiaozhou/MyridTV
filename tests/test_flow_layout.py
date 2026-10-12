"""Graph-layout properties and workflow isolation independent of a browser."""
import copy,random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import myridtv_flow_layout as layout

def node(nid,wid='flow',w=320,h=180):
    return {'id':nid,'type':'smart-image','x':0,'y':0,'w':w,'h':h,'flowLayout':{'workflowId':wid,'layout':'tree_lr'}}

class FlowLayoutTests(unittest.TestCase):
    def test_varied_dags_are_nonoverlapping_rightward_and_repeatable(self):
        rng=random.Random(77)
        for trial in range(20):
            nodes=[node(str(i),w=rng.randint(120,900),h=rng.randint(100,700)) for i in range(30)]
            edges=[{'from':str(rng.randrange(i)),'to':str(i),'kind':'input'} for i in range(1,30)]
            edges.extend({'from':str(rng.randrange(i)),'to':str(i),'kind':'input'} for i in range(2,30,3))
            canvas={'nodes':nodes,'connections':edges}
            layout.layout_workflow(canvas,'flow')
            byid={n['id']:n for n in nodes}
            for i,a in enumerate(nodes):
                for b in nodes[i+1:]:self.assertFalse(layout.overlap((a['x'],a['y'],*layout.node_size(a)),(b['x'],b['y'],*layout.node_size(b))))
            for e in edges:self.assertLessEqual(byid[e['from']]['x']+layout.node_size(byid[e['from']])[0],byid[e['to']]['x'])
            before=copy.deepcopy(canvas);layout.layout_workflow(canvas,'flow');self.assertEqual(canvas,before)

    def test_new_cross_workflow_reference_does_not_rearrange_source_flow(self):
        a=node('asset','assets');a.update(x=1700,y=50)
        b=node('shot','shots');b.update(x=2000,y=1000)
        canvas={'nodes':[a,b],'connections':[]};current=copy.deepcopy(canvas)
        canvas['connections']=[{'from':'asset','to':'shot','kind':'input'}]
        layout.relayout_changed(current,canvas)
        self.assertEqual((a['x'],a['y']),(1700,50))
        self.assertGreaterEqual(b['x'],a['x']+a['w']+layout.GAP_X)
        a['flowLayout']['locked']=True
        current=copy.deepcopy(canvas);a['w']=900
        layout.relayout_changed(current,canvas)
        self.assertGreaterEqual(b['x'],a['x']+900+layout.GAP_X)
        self.assertEqual((a['x'],a['y']),(1700,50))

    def test_generated_group_moves_as_one_footprint(self):
        a=node('a');b=node('b');b['mcpGroupId']='group'
        a.update(w=600,h=400);b.update(x=20,y=42)
        child={'id':'extra','type':'smart-image','x':420,'y':42,'w':380,'h':200}
        group={'id':'group','type':'smart-group','x':0,'y':0,'w':820,'h':320,'memberIds':['b','extra']}
        canvas={'nodes':[a,b,child,group],'connections':[{'from':'a','to':'b','kind':'input'}]}
        layout.layout_workflow(canvas,'flow')
        self.assertEqual((child['x']-b['x'],child['y']-b['y']),(400,0))
        self.assertGreaterEqual(group['x'],a['x']+a['w']+layout.GAP_X)
        self.assertEqual((b['x']-group['x'],b['y']-group['y']),(20,42))

    def test_cycle_through_shared_ancestor_is_rejected(self):
        canvas={'nodes':[node('a'),node('external','other')],
                'connections':[{'from':'a','to':'external'},{'from':'external','to':'a'}]}
        with self.assertRaisesRegex(ValueError,'循环'):layout.layout_workflow(canvas,'flow')

    def test_size_reflow_propagates_in_dependency_order_not_name_order(self):
        a=node('asset','z-assets');b=node('shot','a-shots')
        canvas={'nodes':[a,b],'connections':[{'from':'asset','to':'shot'}]}
        layout.layout_workflow(canvas,'z-assets');layout.layout_workflow(canvas,'a-shots')
        current=copy.deepcopy(canvas);a['w']=1200
        layout.relayout_changed(current,canvas)
        self.assertGreaterEqual(b['x'],a['x']+1200+layout.GAP_X)

if __name__=='__main__':unittest.main()
