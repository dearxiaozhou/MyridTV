"""Actor roster and user-specified scene asset defaults; no fixed scenes."""
ASSET_KINDS={'box':('通用物件',[1,1,1]),'wall':('墙',[4,.15,2.8]),'door':('门',[1,.16,2.2]),'table':('桌子',[1.6,.8,.75]),'chair':('椅子',[.5,.5,.45]),'sofa':('沙发',[2.4,.9,.45]),'bed':('床',[1.5,2,.5]),'tree':('树',[1.8,1.8,3.4]),'car':('车辆',[1.8,4.2,1.5])}
COLORS=[(.16,.40,.59,1),(.72,.36,.18,1),(.38,.57,.30,1),(.55,.35,.65,1),(.68,.57,.22,1),(.25,.60,.59,1),(.65,.30,.43,1),(.47,.49,.56,1)]

def characters(config):
 if config.get('characters') is not None:return config['characters']
 assets=['x_bot','y_bot'] if config['subject']=='both' else [config['subject']]
 return [{'id':'subject_'+str(i+1),'name':'人物'+str(i+1),'asset':asset,'position':[(-.75 if i==0 else .75) if len(assets)>1 else 0,0],'facing':'forward','motion':'sequence'} for i,asset in enumerate(assets)]

def focus_id(config):
 people=characters(config);value=config['focus_subject']
 if value=='group':return value
 if value in {'first','second'}:return people[min(1 if value=='second' else 0,len(people)-1)]['id']
 return value
