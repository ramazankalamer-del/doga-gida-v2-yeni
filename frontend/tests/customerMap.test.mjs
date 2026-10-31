import {test} from 'node:test';
import assert from 'node:assert/strict';
import {hasCoordinates,filterMapCustomers,groupMapCustomers} from '../src/customerMapData.ts';

const customer=(id,latitude,longitude,changes={})=>({id,version:0,name:`Örnek Market ${id}`,contact:'Örnek Yetkili',phone:'',district:'Kadıköy',latitude,longitude,...changes});

test('missing and invalid positions never become a pin at zero',()=>{
 for(const [lat,lon] of [[null,null],[null,29],[41,null],[undefined,29],[NaN,29],[41,Infinity],[91,29],[41,-181],['41','29']]){
  assert.equal(hasCoordinates(customer(1,lat,lon)),false);
 }
 assert.equal(hasCoordinates(customer(1,0,0)),true);
 assert.equal(hasCoordinates(customer(1,-90,180)),true);
});

test('location filters partition customers without losing records',()=>{
 const rows=[customer(1,41,29),customer(2,null,null),customer(3,0,0),customer(4,41,null)];
 assert.equal(filterMapCustomers(rows,'','all').length,4);
 assert.deepEqual(filterMapCustomers(rows,'','located').map(c=>c.id),[1,3]);
 assert.deepEqual(filterMapCustomers(rows,'','missing').map(c=>c.id),[2,4]);
 assert.equal(filterMapCustomers(rows,'','missing').length+filterMapCustomers(rows,'','located').length,rows.length);
});

test('Turkish search matches firm, district and contact, with location filter',()=>{
 const rows=[customer(1,41,29,{name:'IŞIK Gıda',district:'Üsküdar'}),customer(2,null,null,{contact:'İlker Yılmaz'})];
 assert.deepEqual(filterMapCustomers(rows,' ışık ','all').map(c=>c.id),[1]);
 assert.deepEqual(filterMapCustomers(rows,'üsküdar','located').map(c=>c.id),[1]);
 assert.deepEqual(filterMapCustomers(rows,'ilker','missing').map(c=>c.id),[2]);
 assert.deepEqual(filterMapCustomers(rows,'ilker','located'),[]);
 assert.deepEqual(filterMapCustomers(rows,'bulunmayan','all'),[]);
});

test('identical coordinates keep every customer in one selectable group',()=>{
 const rows=[customer(1,41,29),customer(2,41,29),customer(3,42,30),customer(4,null,null)];
 const groups=groupMapCustomers(rows);
 assert.deepEqual(groups.map(group=>group.map(c=>c.id)),[[1,2],[3]]);
 assert.equal(groups.flat().length,3);
 assert.equal(rows.length,4);
});

test('nearby points remain distinct and zero coordinates group correctly',()=>{
 const rows=[customer(1,0,0),customer(2,-0,0),customer(3,41.0000001,29),customer(4,41.0000002,29)];
 assert.deepEqual(groupMapCustomers(rows).map(g=>g.map(c=>c.id)),[[1,2],[3],[4]]);
});

test('empty dataset and filtered-out dataset produce no map points',()=>{
 assert.deepEqual(groupMapCustomers([]),[]);
 assert.deepEqual(groupMapCustomers([customer(1,null,null)]),[]);
 assert.deepEqual(groupMapCustomers(filterMapCustomers([customer(1,41,29)],'yok','all')),[]);
});
