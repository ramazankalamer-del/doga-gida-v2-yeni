import {test} from 'node:test';
import assert from 'node:assert/strict';
import {istanbulWeekday,dailyRouteCustomers,unassignedRouteCustomers,routeDayCounts} from '../src/dailyRouteData.ts';
import {filterMapCustomers,groupMapCustomers} from '../src/customerMapData.ts';

const customer=(id,days,lat=null,lon=null)=>({id,version:0,name:`Örnek Müşteri ${id}`,contact:'Örnek Yetkili',phone:'',district:'Kadıköy',latitude:lat,longitude:lon,route_days:days});

test('customers assigned to multiple days appear once on each chosen day',()=>{
 const rows=[customer(1,[1,4],41,29),customer(2,[4]),customer(3,[6]),customer(4,[])];
 assert.deepEqual(dailyRouteCustomers(rows,1).map(c=>c.id),[1]);
 assert.deepEqual(dailyRouteCustomers(rows,4).map(c=>c.id),[1,2]);
 assert.deepEqual(dailyRouteCustomers(rows,7),[]);
 assert.deepEqual(routeDayCounts(rows),[1,0,0,2,0,1,0]);
});

test('unassigned customers remain available for planning without inventing a day',()=>{
 const rows=[customer(1,[]),customer(2,[1]),customer(3,undefined)];
 assert.deepEqual(unassignedRouteCustomers(rows).map(c=>c.id),[1,3]);
 assert.deepEqual(dailyRouteCustomers(rows,1).map(c=>c.id),[2]);
 assert.deepEqual(unassignedRouteCustomers([]),[]);
});

test('day list, GPS filter and map points stay in the selected route',()=>{
 const rows=[customer(1,[1],41,29),customer(2,[1]),customer(3,[4],42,30),customer(4,[1],41,29)];
 const route=dailyRouteCustomers(rows,1);
 assert.equal(route.length,3);
 assert.deepEqual(filterMapCustomers(route,'','missing').map(c=>c.id),[2]);
 assert.deepEqual(groupMapCustomers(filterMapCustomers(route,'','located')).map(g=>g.map(c=>c.id)),[[1,4]]);
 assert.deepEqual(filterMapCustomers(route,'Müşteri 3','all'),[]);
});

test('editing or clearing route days immediately changes membership and counts',()=>{
 const row=customer(1,[1]);
 assert.equal(dailyRouteCustomers([row],1).length,1);
 const updated={...row,route_days:[4,5]};
 assert.equal(dailyRouteCustomers([updated],1).length,0);
 assert.deepEqual(routeDayCounts([updated]),[0,0,0,1,1,0,0]);
 assert.equal(unassignedRouteCustomers([{...updated,route_days:[]}]).length,1);
});

test('today uses Istanbul at midnight and week boundaries, independently of host timezone',()=>{
 assert.equal(istanbulWeekday(new Date('2026-10-31T12:00:00Z')),6);
 assert.equal(istanbulWeekday(new Date('2026-11-01T20:59:59Z')),7);
 assert.equal(istanbulWeekday(new Date('2026-11-01T21:00:00Z')),1);
});

test('invalid weekday does not reveal customers from another route',()=>{
 const rows=[customer(1,[1])];
 for(const day of [0,8,-1,1.5,NaN])assert.deepEqual(dailyRouteCustomers(rows,day),[]);
});
import {istanbulDate,dateWeekday,routeDateForDay} from '../src/dailyRouteData.ts';
test('visit date uses Istanbul calendar and weekdays stay in the selected week',()=>{
 assert.equal(istanbulDate(new Date('2026-10-31T21:00:00Z')),'2026-11-01');
 assert.equal(dateWeekday('2026-11-01'),7);
 assert.equal(routeDateForDay('2026-11-01',1),'2026-10-26');
 assert.equal(routeDateForDay('2027-01-01',1),'2026-12-28');
 assert.equal(routeDateForDay('2028-03-01',2),'2028-02-29');
});
