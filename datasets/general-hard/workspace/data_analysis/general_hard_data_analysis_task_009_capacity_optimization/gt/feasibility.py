"""Exact integer/cent accounting of an arbitrary proposed allocation."""
from collections import defaultdict
from decimal import Decimal
def cents(value):
    amount=Decimal(str(value))*100
    if amount!=amount.to_integral_value():raise ValueError('Source money not exact cents')
    return int(amount)
def evaluate(data,allocation):
    demand={r['sku_id']:r for r in data['demand']};plants={r['plant_id']:r for r in data['plants']};routes={(r['plant_id'],r['sku_id']):r for r in data['routes']};costs={(r['plant_id'],r['sku_id']):r for r in data['costs']};recipe={(r['sku_id'],r['material_id']):r['units_per_item'] for r in data['recipes']}
    if set(allocation)!=set(routes):raise ValueError('Allocation must cover all 36 routes')
    if any(type(value) is not int for value in allocation.values()):raise ValueError('GT evaluator only accepts exact integer quantities; never rounds a candidate fraction')
    checks={};delivered=defaultdict(int);plant_units=defaultdict(int);plant_hours=defaultdict(int);product_cost=0;transport=0;line_total=0;lines=[]
    for key,x in allocation.items():
        plant,sku=key;route=routes[key];price=costs[key];checks['nonnegative/'+plant+'/'+sku]=x>=0;checks['route/'+plant+'/'+sku]=x==0 or bool(route['eligible']) and route['min_batch']<=x<=route['max_units'];delivered[sku]+=x;plant_units[plant]+=x;plant_hours[plant]+=x*route['labour_per_unit'];p=x*cents(price['variable_cost']);t=x*cents(price['transport_cost']);setup=cents(price['line_setup_fee']) if x>0 else 0;product_cost+=p;transport+=t;line_total+=setup
        lines.append({'plant_id':plant,'sku_id':sku,'units':x,'line_active':x>0,'production_cents':p,'transport_cents':t,'setup_cents':setup,'line_total_cents':p+t+setup})
    product_rows=[]
    for sku,row in demand.items():
        checks['demand/'+sku]=row['minimum_service']<=delivered[sku]<=row['demand_units'];product_rows.append({'sku_id':sku,'priority':row['priority'],'demand_units':row['demand_units'],'minimum_service':row['minimum_service'],'served_units':delivered[sku],'unmet_units':row['demand_units']-delivered[sku]})
    plant_rows=[];activation=0
    for plant,row in plants.items():
        fees={cents(c['plant_activation_fee']) for c in costs.values() if c['plant_id']==plant};assert len(fees)==1;fee=next(iter(fees)) if plant_units[plant]>0 else 0;activation+=fee;checks['unit_capacity/'+plant]=plant_units[plant]<=row['unit_capacity'];checks['labour_capacity/'+plant]=plant_hours[plant]<=row['labour_capacity'];plant_rows.append({'plant_id':plant,'active':plant_units[plant]>0,'used_units':plant_units[plant],'unit_capacity':row['unit_capacity'],'unit_slack':row['unit_capacity']-plant_units[plant],'used_labour':plant_hours[plant],'labour_capacity':row['labour_capacity'],'labour_slack':row['labour_capacity']-plant_hours[plant],'activation_cents':fee})
    material_rows=[]
    for m in data['materials']:
        key=m['material_id'];use=sum(delivered[sku]*recipe[sku,key] for sku in demand);checks['material/'+key]=use<=m['available_units'];material_rows.append({'material_id':key,'used_units':use,'available_units':m['available_units'],'slack':m['available_units']-use})
    total=product_cost+transport+line_total+activation;budget=cents(data['budget']);checks['budget']=total<=budget
    gaps=[sum(r['unmet_units'] for r in product_rows if r['priority']==priority) for priority in [1,2,3]]
    controls={'priority1_unmet':gaps[0],'priority2_unmet':gaps[1],'priority3_unmet':gaps[2],'production_cents':product_cost,'transport_cents':transport,'setup_cents':line_total,'activation_cents':activation,'total_cents':total,'budget_cents':budget,'budget_slack_cents':budget-total,'all_demand_satisfied':all(r['unmet_units']==0 for r in product_rows)}
    return {'feasible':all(checks.values()),'checks':checks,'objective':gaps+[total],'allocations':lines,'products':product_rows,'plants':plant_rows,'materials':material_rows,'controls':controls}
