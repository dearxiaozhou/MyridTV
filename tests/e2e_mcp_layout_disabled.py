"""Default-off layout preserves node positions through gateway and size saves."""
import copy,json
from e2e_canvas_gateway import api,call,read,positions,ROOT

def main():
 policy=call('describe')['layout_policy']
 assert 'disabled' in policy
 schema=call('describe',{'action':'create_generation_node'})['params_schema']
 assert {'x','y'}<=set(schema['properties'])
 cid=call('create',{'title':'MCP关闭排版验收'})['canvas_id']
 created=call('create_generation_node',{'title':'原生节点','prompt':'不提交生成任务，仅验证位置','x':120,'y':900},canvas_id=cid)
 n=next(n for n in read(cid)['nodes'] if n['id']==created['node_id'])
 assert 'flowLayout' not in n
 assert (n['x'],n['y'])==(120,900)
 flow={'nodes':[{'id':'a','type':'generation','title':'A','prompt':'保持手动位置','x':500,'y':600},
                {'id':'b','type':'generation','title':'B','prompt':'保持手动位置','x':1300,'y':300}],
       'edges':[{'from':'a','to':'b','kind':'input'}]}
 reply=call('upsert_flow',flow,canvas_id=cid,workflow_id='manual-flow')
 assert reply['layout_disabled'] and reply['moved']==[] and reply['layout']=='manual'
 before=positions(read(cid))
 call('upsert_flow',{'nodes':[{'id':'a','prompt':'只更新文字'}]},canvas_id=cid,workflow_id='manual-flow')
 assert positions(read(cid))==before
 call('layout_flow',canvas_id=cid,workflow_id='manual-flow')
 assert positions(read(cid))==before
 # Old saved tree_lr markers must no longer trigger size-change reflow either.
 saved=read(cid)
 for node in saved['nodes']:
  if node['id'] in ['a','b']:node['flowLayout']['layout']='tree_lr'
 next(n for n in saved['nodes'] if n['id']=='a').update(w=900,h=700,cardSize={'width':900,'height':700})
 api('/api/canvases/'+cid,saved,'PUT')
 assert positions(read(cid))==before
 assert len(read(cid)['connections'])==1
 (ROOT/'_verification/mcp-layout-disabled-audit.json').write_text(json.dumps({'canvas_id':cid,'checks':['gateway reports disabled','native explicit coordinates accepted','no enrollment','upsert preserves coordinates','text update no movement','layout_flow no movement','legacy size-save no movement','connections preserved']},indent=2),encoding='utf-8')
 print('MCP automatic layout disabled: 8 checks passed')

if __name__=='__main__':main()
