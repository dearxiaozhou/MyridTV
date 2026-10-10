"""Concurrent full-canvas saves must compare-and-write atomically."""
import concurrent.futures, tempfile, threading, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import myridtv_canvas_store as store
from myridtv_core import CanvasConflictError

class SaveRevisionTests(unittest.TestCase):
    def test_same_revision_has_one_winner_and_deleted_nodes_stay_deleted(self):
        with tempfile.TemporaryDirectory() as root:
            store.configure(Path(root),Path(root),lambda:None,lambda c:None,lambda p:None,lambda c:None)
            canvas=store.create_canvas_record({'nodes':[{'id':'old','type':'smart-image','images':[]}]})
            gate=threading.Barrier(6)
            def save(i):
                gate.wait()
                try:
                    result=store.save_canvas_record(canvas['id'],{'base_updated_at':canvas['updated_at'],'nodes':[]})
                    return result
                except CanvasConflictError:
                    return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(save,range(6)))
            winners=[r for r in results if r]
            self.assertEqual(len(winners),1)
            self.assertGreater(winners[0]['updated_at'],canvas['updated_at'])
            self.assertEqual(winners[0]['deleted'][0]['id'],'old')
            stale=dict(canvas)
            with self.assertRaises(CanvasConflictError): store.save_canvas_record(canvas['id'],stale)
            current=winners[0]
            saved=store.save_canvas_record(canvas['id'],{'base_updated_at':current['updated_at'],'nodes':canvas['nodes']})
            self.assertEqual(saved['nodes'],[])

    def test_explicit_text_clear_does_not_fall_back_to_content(self):
        self.assertEqual(store._normalize_node({'id':'n','text':'','content':'old'})['content'],'')

if __name__=='__main__': unittest.main()
