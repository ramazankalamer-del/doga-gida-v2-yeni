export type MapCustomer = {id:number;version:number;name:string;contact:string;phone:string;district:string;latitude:number|null;longitude:number|null};
export type LocatedCustomer = MapCustomer & {latitude:number;longitude:number};
export type LocationFilter = 'all'|'located'|'missing';

export function hasCoordinates(customer:MapCustomer):customer is LocatedCustomer {
 return typeof customer.latitude==='number'&&Number.isFinite(customer.latitude)&&Math.abs(customer.latitude)<=90
  &&typeof customer.longitude==='number'&&Number.isFinite(customer.longitude)&&Math.abs(customer.longitude)<=180;
}

export function filterMapCustomers(customers:MapCustomer[],query:string,filter:LocationFilter):MapCustomer[]{
 const term=query.trim().toLocaleLowerCase('tr');
 return customers.filter(c=>(!term||`${c.name} ${c.district} ${c.contact}`.toLocaleLowerCase('tr').includes(term))
  &&(filter==='all'||(filter==='located'?hasCoordinates(c):!hasCoordinates(c))));
}

export function groupMapCustomers(customers:MapCustomer[]){
 const groups=new Map<string,LocatedCustomer[]>();
 for(const customer of customers){
  if(!hasCoordinates(customer))continue;
  const key=JSON.stringify([customer.latitude,customer.longitude]);
  const group=groups.get(key);
  if(group)group.push(customer);else groups.set(key,[customer]);
 }
 return [...groups.values()];
}
