import {test} from 'node:test';
import assert from 'node:assert/strict';
import {retryRouteCustomers} from '../src/retryRouteData.ts';
import {dailyRouteCustomers} from '../src/dailyRouteData.ts';
import {filterMapCustomers} from '../src/customerMapData.ts';
const customer=(id,days,latitude=null,longitude=null)=>({id,name:`Müşteri ${id}`,contact:'Yetkili',district:'Test',route_days:days,latitude,longitude});
test('includes both explicit unsuccessful visits and customers without a visit record',()=>{
 const rows=[customer(3,[1]),customer(1,[1]),customer(2,[1])];
 assert.deepEqual(retryRouteCustomers(rows,[{customer_id:1,visited:1},{customer_id:2,visited:0}]).map(c=>c.id),[3,2]);
});
test('selected weekday and saved order remain scoped; outside customer visits cannot leak',()=>{
 const rows=[customer(3,[1]),customer(2,[4]),customer(1,[1]),customer(4,[])];
 const scope=dailyRouteCustomers(rows,1);
 assert.deepEqual(retryRouteCustomers(scope,[{customer_id:2,visited:0}]).map(c=>c.id),[3,1]);
});
test('successful visit removes customer, reversal restores original route position',()=>{
 const rows=[customer(2,[1]),customer(1,[1])];
 assert.deepEqual(retryRouteCustomers(rows,[{customer_id:2,visited:1}]).map(c=>c.id),[1]);
 assert.deepEqual(retryRouteCustomers(rows,[{customer_id:2,visited:0}]).map(c=>c.id),[2,1]);
});
test('empty daily records reset pending membership and GPS filters do not discard missing locations',()=>{
 const rows=[customer(1,[1]),customer(2,[1],41,29)];
 const pending=retryRouteCustomers(rows,[]);
 assert.equal(pending.length,2);
 assert.deepEqual(filterMapCustomers(pending,'','missing').map(c=>c.id),[1]);
 assert.equal(retryRouteCustomers([],[]).length,0);
 assert.equal(retryRouteCustomers(rows,[{customer_id:1,visited:1},{customer_id:2,visited:1}]).length,0);
});
