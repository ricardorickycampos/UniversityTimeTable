# UniTime Data Shape

## Rooms 
Total : 63 

### Fields 
| Name | Description | Type |
|---|---|---|
|Id | Unique room ID | int 
| Capacity | Number of seats | int |
| Constraint | Whether this room participates in conflict check (true for all 63) | bool | 
| Location | Rooms location (stored but ununsed - no travel time check) | int,int (x,y) | 
| Sharing | which department can use the room during which time block (13 out of 63 have this) | String | 

Sharing block is a string such as "FFF000111XXX..." where each char covers a 30 min chunk.
F = Free
X = Unavailable
Digit = mapped to deparment that can use it. 

## Classes 
Total : 896 

### Fields 
| Name | Description | Type |
|---|---|---|
| id | unique class id | 