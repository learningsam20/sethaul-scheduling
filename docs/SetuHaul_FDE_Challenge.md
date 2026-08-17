



#### **SetuHaul FDE Challenge** 

# **SETUHAUL LOGISTICS** 

## **Driver Exception and Dock Slot Coordination** 

_An open-ended FDE classroom problem FDE classroom case | August 2026_ 

### **The central challenge** 

A driver who may miss a warehouse appointment needs help through chat. The difficult part is not answering one driver. The difficult part is handling many drivers at the same time when several of them need the same limited set of feasible receiving slots. 

### **What this brief contains** 

- A plain-English explanation of freight, warehouses, docks and appointments 

- A system and data primer before the technical problem begins 

- The reason an AI agent is useful — and the decisions it should not make 

- Driver-facing conversation and simultaneous-capacity challenges 

- A realistic data package, open design questions and an optional facility-level scheduling extension 

_Important: This document describes the business problem and the available business data. It does not prescribe an agent framework, tool set, storage design, concurrency mechanism, allocation algorithm or deployment pattern._ 

##### **1. · Company and Business Context** 

#### **1.1 The company** 

SetuHaul Logistics Pvt. Ltd. is a mid-sized third-party logistics company operating full-truckload road freight across North and West India. It coordinates company-owned and contracted trucks carrying domestic shipments to factories, warehouses and distribution centres. 

The operating figures below define SetuHaul’s current scale for this problem brief. 

|**CLASSROOM OPERATING PROFILE**|**OPERATING VALUE**|
|---|---|
|**Loads coordinated each day**|280-360|
|**Destination facilities**|6|





For doubts reach out to: <u>delivery@fde.academy</u> 

1 





|**CLASSROOM OPERATING PROFILE**|**OPERATING VALUE**|
|---|---|
|**Dock doors across all facilities**|32|
|**Scheduled receiving appointments per day**|190-240|
|**Driver exception messages on a normal day**|15-25|
|**Messages during a disruption spike**|20-35 within 30 minutes|
|**Operations coordinators per shift**|5|



#### **1.2 Why delays matter** 

A freight plan is a chain of commitments: the right truck, load, route, arrival time, warehouse capacity, unloading labour and stakeholder communication. A late arrival can break several commitments together. 

External scale reference. ATRI reported that drivers experienced detention at 39.3% of stops in 2023. It estimated more than 135 million annual detention hours, 72 million gallons of diesel wasted while idling and $11.5 billion in productivity losses. These are U.S. industry figures used only to show the scale of waiting and coordination problems. 

One delay is manageable. A wave of delays is not. Rain, congestion, road closures or loading backlogs can create many incomplete driver messages while the number of usable replacement slots remains limited. 

##### **2. · Freight Operations in Plain English** 

#### **2.1 Follow one truck from origin to delivery** 

|**STAGE**|**WHAT HAPPENS**|**BUSINESS DATA CREATED OR**<br>**UPDATED**|
|---|---|---|
|**1. Shipment**<br>**planned**|A load is created with origin, destination,<br>goods and required delivery time.|shipment_id, origin, destination, product<br>class, priority|
|**2. Driver and**<br>**vehicle**<br>**assigned**|A carrier assigns a driver and truck to move<br>the load.|driver_id, vehicle_id, carrier_id|
|**3.**<br>**Warehouse**<br>**appointment**<br>**booked**|The destination reserves a receiving window<br>for unloading.|facility_id, dock_id, slot_id,<br>appointment_id|
|**4. Truck**<br>**travels**|The driver moves toward the destination. The<br>original ETA remains in the plan, and the|planned_eta, latest_declared_eta,<br>eta_updated_at, shipment status|





For doubts reach out to: <u>delivery@fde.academy</u> 

2 





|**STAGE**|**WHAT HAPPENS**<br>driver may declare a revised ETA when<br>conditions change.|**BUSINESS DATA CREATED OR**<br>**UPDATED**|
|---|---|---|
|**5. Gate and**<br>**yard arrival**|The truck checks in and may wait inside the<br>facility yard.|actual_gate_in_at, arrival_status,<br>queue_status|
|**6. Dock and**<br>**unload**|The truck backs into a loading bay, goods are<br>unloaded, and the visit is completed.|dock-in, unload start/end, proof of delivery|



_Simple movement: Origin warehouse → truck in transit → destination gate → yard/waiting area → dock door/loading bay → unloading → exit_ 

#### **2.2 Important terms** 

|**TERM**|**PLAIN-ENGLISH MEANING**|
|---|---|
|**Facility / warehouse**|The destination site that receives goods. It may be a factory, warehouse or<br>distribution centre.|
|**Gate**|The controlled entrance where the driver and vehicle are checked in.|
|**Yard**|The open area inside or near the facility where trucks wait before being called<br>to a dock.|
|**Dock door / loading bay**|The physical position where a truck reverses against the warehouse building so<br>goods can be loaded or unloaded. “Dock station” is not the preferred term in<br>this brief.|
|**Dock appointment**|A booking that says a particular shipment is expected during a defined<br>receiving window.|
|**Appointment slot**|The start and end time available for a dock or a unit of receiving capacity, for<br>example 7:30-8:00 PM.|
|**Compatible dock**|A dock that can physically and operationally handle the truck and goods — for<br>example vehicle length, refrigeration, product type or required equipment.|
|**ETA**|Estimated time of arrival. The first ETA comes from the shipment plan. If<br>conditions change, the driver may declare a revised ETA. This exercise does<br>not require live GPS tracking.|





For doubts reach out to: <u>delivery@fde.academy</u> 

3 





|**TERM**|**PLAIN-ENGLISH MEANING**|
|---|---|
|**Exception**|An event such as a breakdown, traffic delay or late departure that makes the<br>original plan uncertain.|
|**Detention**|Time a driver spends waiting at a facility beyond the expected loading or<br>unloading period.|



##### **3. · Where the Data Comes From** 

A driver message does not contain the complete answer. Different systems hold different parts of the business truth. Students should understand these systems before designing any agent or workflow. 

|**BUSINESS SYSTEM**|**WHAT IT KNOWS**|**CLASSROOM DATA**|
|---|---|---|
|**TMS — Transportation**<br>**Management System**|Shipment, driver, vehicle, origin,<br>destination, original plan, planned ETA<br>and shipment status.|drivers, vehicles, shipments|
|**Dock scheduler /**<br>**WMS**|Facilities, dock doors, receiving windows,<br>existing bookings, operating rules and<br>capacity.|facilities, docks, appointment_slots,<br>appointments, facility_rules|
|**Gate / yard check-in**|Whether a truck has actually arrived, when<br>it entered, and whether it is waiting,<br>docked or completed.|facility_checkins|
|**Driver chat and ETA**<br>**updates**|What happened, the latest ETA declared<br>by the driver, questions, preferences and<br>constraints.|driver_exceptions, eta_updates,<br>chat_messages|
|**Contact / messaging**<br>**system**|Warehouse, customer and carrier contacts<br>plus confirmations or replies.|contacts, operational_messages|



### **Why integration matters** 

The shipment plan provides the original ETA. The driver can declare a revised ETA. Gate check-in establishes actual arrival. The warehouse system knows dock capacity, while messaging carries confirmations. No single system contains the full operational answer. 

- **3.1 The basic data relationships** 



For doubts reach out to: <u>delivery@fde.academy</u> 

4 





|**RELATIONSHIP**|**MEANING**|
|---|---|
|**driver → shipment**|Which active load the person in chat is currently moving.|
|**shipment → vehicle**|Which truck must be checked for dock compatibility.|
|**shipment → destination facility**|Which warehouse schedule and local rules apply.|
|**shipment → eta_updates**|The original planned ETA and the latest ETA explicitly declared by the<br>driver.|
|**shipment → facility_checkins**|Whether the truck has arrived and whether it is waiting at the gate, yard<br>or dock.|
|**facility → dock → slot**|Which physical receiving capacity is available at a specific time.|
|**shipment → appointment →**<br>**slot**|Which receiving window is currently planned for the load.|
|**exception → thread →**<br>**messages**|Which conversation belongs to which reported operational problem.|



##### **4. · One Example Across the Data** 

Use one connected example when introducing the tables. Students should be able to trace a single driver message into the relevant rows before they think about tools or agents. 

### **Driver message** 

_“Tyre damaged near Neemrana. Repair may take 45 minutes. Can I get a slot after 7 PM? I must leave before 9 PM for another pickup.”_ 

|**TABLE**|**EXAMPLE ROW**|**WHAT THE ROW TELLS US**|
|---|---|---|
|**drivers**|DRV-027 | Ravi Kumar | carrier CAR-08|Who is speaking and which carrier is<br>responsible.|
|**vehicles**|VEH-031 | 32-foot dry van | active|The truck type that a dock must support.|
|**shipments**|SHP-1042 | DRV-027 | VEH-031 |<br>destination FAC-JPR-01 | planned ETA<br>17:20|The active movement, destination and<br>original expected arrival.|
|**eta_updates**|ETA-880 | SHP-1042 | driver | revised ETA<br>19:10 | declared 16:08|The latest arrival time explicitly declared<br>by the driver.|





For doubts reach out to: <u>delivery@fde.academy</u> 

5 





|**TABLE**|**EXAMPLE ROW**|**WHAT THE ROW TELLS US**|
|---|---|---|
|**facilities**|FAC-JPR-01 | Jaipur DC | open<br>06:00-23:00|The warehouse, local operating hours<br>and location.|
|**docks**|DOCK-04 | FAC-JPR-01 | dry freight | max<br>32-foot|A physical loading bay that may be<br>compatible.|
|**appointment_slots**|SLOT-1938 | DOCK-04 | 17:30-18:00 |<br>open|A unit of receiving time and capacity.|
|**appointments**|APT-552 | SHP-1042 | SLOT-1938 |<br>confirmed|The driver’s original booked warehouse<br>window.|
|**facility_checkins**|No row yet for SHP-1042|The truck has not reached the<br>destination gate. Once it arrives, actual<br>gate-in and queue status become<br>available.|
|**driver_exceptions**|EXC-778 | SHP-1042 | tyre issue |<br>reported 16:05|The operational problem being handled.|
|**chat_messages**|MSG-9001 | EXC-778 | driver | free-text<br>message|The exact conversational input and its<br>thread.|
|**facility_rules**|FAC-JPR-01 | dry vans up to 32 ft |<br>effective all day|A local eligibility rule that affects feasible<br>choices.|



#### **4.1 Questions the data must answer** 

- Which active shipment does DRV-027 mean? 

- What is the current appointment and when does it become infeasible? 

- What is the revised ETA, and how uncertain is it? 

- Has the truck already arrived, and is it waiting at the gate, yard or dock? 

- Which docks can accept VEH-031 and this product class? 

- Which later slots are still usable after considering other appointments and requests? 

- Has a slot merely been shown, temporarily held, requested or confirmed? 

_The example values are illustrative. The final student dataset should contain many linked records, imperfect data and simultaneous requests._ 

##### **5. · Current Operating Reality** 

#### **5.1 Parties involved** 



For doubts reach out to: <u>delivery@fde.academy</u> 

6 





|**PARTY**|**WHAT IT KNOWS**|**WHAT IT NEEDS DURING AN**<br>**EXCEPTION**|
|---|---|---|
|**Driver**|Physical location, breakdown, traffic and<br>likely delay.|Clear choices, instructions and<br>confirmation.|
|**Dispatcher /**<br>**carrier**|Vehicle assignment and driver<br>availability.|A revised plan and escalation status.|
|**SetuHaul**<br>**operations**|Shipment plan, customer commitment<br>and open exceptions.|A consistent view across many<br>simultaneous requests.|
|**Warehouse**<br>**planner**|Dock capacity, labour, equipment and<br>local rules.|Feasible arrivals without overbooking.|
|**Consignee /**<br>**customer**|Inventory or production dependency.|Reliable revised arrival information.|



#### **5.2 What happens today** 

**1.** A driver sends a short message such as: “Tyre damaged near Neemrana. Around 90 minutes late.” 

**2.** An operations coordinator identifies the driver, active shipment, destination and existing appointment. 

**3.** The coordinator checks whether the current appointment is still possible. 

**4.** The coordinator checks the facility schedule, local rules and other pending requests. 

**5.** The coordinator discusses or books a revised plan and informs the required parties. 

**6.** Replies, cancellations and changing ETAs can force the plan to be reconsidered. 

### **Why a small message creates a large workflow** 

The message is unstructured, but the decision depends on shipment context, the latest declared ETA, actual arrival status, dock capacity, facility rules, competing requests and confirmation status. No single message or system contains the complete answer. 

#### **5.3 What cannot be guessed** 

|**QUESTION**|**WHY IT CANNOT BE GUESSED**|
|---|---|
|**Which shipment is affected?**|A driver can have different assignments on different days.|
|**Is the stated delay the full**<br>**impact?**|Repair time and revised arrival time are not always the same.|





For doubts reach out to: <u>delivery@fde.academy</u> 

7 





|**QUESTION**|**WHY IT CANNOT BE GUESSED**|
|---|---|
|**What is the latest ETA?**|The original plan may be stale, and the driver may correct the ETA over<br>several messages.|
|**Has the truck already arrived?**|Actual gate-in and queue status come from facility operations, not from<br>the original appointment.|
|**Which slots are feasible?**|Availability and eligibility differ by load, vehicle and time.|
|**Is a slot still available?**|Another conversation may be trying to claim it at the same time.|
|**Has the warehouse confirmed?**|A proposed change and a committed appointment are not the same.|



##### **6. · Why Use an AI Agent Here?** 

SetuHaul does not need an LLM to calculate warehouse capacity or safely allocate scarce slots. Those are structured operational decisions. The AI is useful because the work begins and ends through messy, multi-turn human conversation. 

#### **6.1 Why a fixed form is not enough** 

A form works well when every driver knows the shipment number, delay, revised ETA and desired action. Real messages are often incomplete, informal and corrected over several turns. 

|**DRIVER SAYS**|**WHAT MUST BE UNDERSTOOD OR CLARIFIED**|
|---|---|
|“I will be around two hours late.”|Which shipment, why, and whether two hours is the total ETA impact.|
|“Anything after 7?”|Which facility, compatible options, and whether the driver is asking to<br>view or book.|
|“The second one works, but I<br>need to leave by 9.”|Which previously shown option and whether unloading can finish<br>before the next commitment.|
|“Has it been confirmed?”|The current status of the same exception thread and latest warehouse<br>response.|



#### **6.2 What the AI layer contributes** 

- Understands free-text driver messages and informal wording. 

- Asks only for information that is missing or ambiguous. 

- Maintains context across follow-up questions and corrections. 

- Connects conversational intent to structured business data and controlled actions. 

- Explains available choices, constraints and status in simple language. 



For doubts reach out to: <u>delivery@fde.academy</u> 

8 





- Continues the same thread when the driver returns later for an update. 

#### **6.3 What the AI should not decide by itself** 

- Whether two drivers can be promised the same capacity. 

- Whether a vehicle is physically compatible with a dock. 

- How scarce capacity is prioritised when business rules conflict. 

- Whether a booking is committed successfully in the system of record. 

- Driver-safety, legal, penalty or exceptional commercial decisions. 

### **The FDE lesson** 

The AI agent is the conversational coordination layer. Students must still design a trustworthy operational layer for feasibility, freshness, capacity, concurrent requests and confirmation. The brief intentionally leaves that design open. 

##### **7. · The Problem Students Must Solve** 

### **Problem statement** 

How might SetuHaul provide a conversational way for drivers to report delays, ask questions and consider revised appointments, while ensuring that many simultaneous requests are handled against limited warehouse capacity without infeasible or conflicting promises? 

#### **7.1 First-level challenge: one driver** 

- Understand what happened and what information is missing. 

- Connect the conversation to the correct active shipment and original appointment. 

- Help the driver understand whether the original plan still works. 

- Show suitable possibilities and answer follow-up questions. 

- Keep the driver informed about whether a change is proposed, pending or confirmed. 

#### **7.2 The real challenge: many drivers** 

The system may receive many requests at once. Five drivers may ask for a 6:00 PM window when only one compatible dock is free. Two conversations may read the same availability before either completes. A cancellation may free a slot while another driver is deciding. A high-priority load may appear after lower-priority choices have already been discussed. 



For doubts reach out to: <u>delivery@fde.academy</u> 

9 





|**CONCURRENT EVENT**|**BUSINESS RISK**|
|---|---|
|**Two drivers choose the same slot**<br>**within seconds.**|Double booking or a broken promise.|
|**A shown slot disappears before**<br>**confirmation.**|The driver receives stale guidance.|
|**A high-priority load arrives after earlier**<br>**requests.**|Unclear fairness or service-level breach.|
|**A driver changes ETA during the**<br>**conversation.**|Previously discussed options may become infeasible.|
|**A warehouse blocks one dock**<br>**unexpectedly.**|Several appointments may require reconsideration.|
|**A driver retries or sends duplicate**<br>**messages.**|Duplicate requests or repeated actions.|



### **The allocation question** 

The challenge is not simply “find an empty row.” Students must decide what availability means while conversations are active, how requests compete, when a promise becomes binding, and what happens when demand is greater than capacity. 

#### **7.3 Optional extension: a scheduling engine as a tool** 

The conversational agent handles one driver’s message and questions. Students may optionally design a separate scheduling engine that considers all relevant trucks for one facility together. The agent can call this engine as a controlled tool. The engine receives structured operational data and returns a proposed schedule or ranked feasible options; it does not interpret free text. 

### **Data boundary** 

This exercise does not require live GPS tracking. The scheduling engine uses the original planned ETA, the latest ETA explicitly declared by the driver, and actual gate-in time once a truck reaches the facility. 

### **Example: several trucks compete for two dock doors** 

At 5:25 PM, the Jaipur facility has two dock doors. The latest operational snapshot looks like this: 



For doubts reach out to: <u>delivery@fde.academy</u> 

10 





|**TRUCK OR FACILITY STATE**|**LATEST KNOWN OPERATING DATA**|
|---|---|
|**SHP-201 — arrived early**|Booked for 5:30 PM; gate-in at 5:05 PM; waiting in the yard; 40-minute<br>unload; compatible with D1 or D2.|
|**SHP-202 — arrived late**|Booked for 5:00 PM; gate-in at 5:25 PM; waiting at the gate; 30-minute<br>unload; compatible only with D2.|
|**SHP-203 — expected late**|Booked for 5:45 PM; not yet arrived; driver updated ETA to 6:35 PM;<br>45-minute unload; compatible with D1 or D2.|
|**SHP-204 — currently**<br>**unloading**|Already on D1; expected to finish at 5:40 PM. This work cannot simply be<br>moved.|
|**Facility capacity**|D1 is occupied until about 5:40 PM. D2 is free now. Operating hours<br>continue until 11:00 PM.|



The question is no longer only “find a later slot for SHP-203.” The facility must decide what to do with the early truck, the late truck already waiting, the truck expected much later, and the work already in progress. A scheduling tool may propose a facility-wide sequence while respecting commitments and capacity. 

**How the business data maps to a scheduling model** 

|**BUSINESS CONCEPT**|**SCHEDULING-MODEL INTERPRETATION**|
|---|---|
|**Truck / shipment**|A job that requires service.|
|**Dock door**|A machine or limited resource.|
|**Original or latest**<br>**driver-declared ETA**|A release time: the truck should not be scheduled before it can arrive.|
|**Actual gate-in**|Evidence that the truck is available now and may already be waiting.|
|**Expected unloading duration**|Processing time required on the dock.|
|**Booked appointment**|A promised time window, due time or service commitment.|
|**Vehicle and product**<br>**compatibility**|The set of dock doors that are allowed for that truck.|
|**Shipment priority**|A weight or penalty when waiting or lateness is calculated.|
|**Truck already unloading or a**<br>**protected commitment**|A fixed task or constraint that the new schedule should not move.|



### **What students may explore** 



For doubts reach out to: <u>delivery@fde.academy</u> 

11 





- A simple dispatching baseline such as appointment-first, first-arrived-first-served, earliest due time or shortest unloading time. 

- A transparent score-based heuristic combining waiting time, lateness, priority and dock compatibility. 

- Constraint programming or mixed-integer optimisation for assigning trucks to dock-time intervals. 

- Rolling-horizon scheduling that recalculates when a driver updates ETA, a truck checks in, unloading completes, a slot is cancelled or a dock becomes unavailable. 

- The objective itself: minimise total waiting, appointment lateness, overtime, priority violations or unnecessary changes to an already communicated schedule. 

_This is optional. A student team can keep the scheduling tool rule-based, provided the rules are explicit and the team demonstrates what happens when several trucks compete. The optional engine is facility-level; national route or fleet optimisation remains outside the assignment._ 

### **Optional operational-research references** 

**1.** Google OR-Tools — Scheduling overview. A practical introduction to resource-constrained scheduling. 

**2.** Google OR-Tools — The Job Shop Problem. Useful for thinking of trucks as jobs and dock doors as machines. 

**3.** Monemia and Gelareh — Dock Assignment and Truck Scheduling Problem. A research example focused directly on dock assignment, truck scheduling and resource constraints. 

##### **8. · Make the Experience Genuinely Chat-Based** 

The driver should be able to report an exception, ask practical questions, compare options, add personal operating constraints, change a choice and return later for status. The conversation is therefore both informational and operational. 

|**CONVERSATION**<br>**TYPE**|**EXAMPLE DRIVER MESSAGE**|
|---|---|
|**Report**|“I am stuck near Neemrana and may be 90 minutes late.”|
|**Clarify**|“Repair will take 45 minutes, but traffic after that is uncertain.”|
|**Ask for options**|“What are the next two slots after 6 PM?”|
|**Add a constraint**|“I need to leave by 9 PM for my next pickup.”|
|**Compare**|“Which option has the shortest expected waiting time?”|
|**Facility question**|“Does the 7:30 slot accept a 32-foot vehicle?”|
|**Choose**|“Take the second option.”|
|**Change mind**|“Do not book 7:30. Check tomorrow morning.”|





For doubts reach out to: <u>delivery@fde.academy</u> 

12 





|**CONVERSATION**<br>**TYPE**|**EXAMPLE DRIVER MESSAGE**|
|---|---|
|**Status**|“Has the warehouse confirmed my new slot?”|
|**Fallback**|“There is no slot today. What should I do next?”|



#### **8.1 Conversation identity** 

|**CONCEPT**|**RECOMMENDED CLASSROOM MEANING**|
|---|---|
|**User / session identity**|The authenticated driver_id.|
|**Conversation thread**|One active shipment exception request.|
|**Request identifier**|A unique exception_id connected to the thread.|
|**Shipment context**|The shipment affected by this exception.|
|**Conversation state**|What is known, what remains unclear and the status of any proposed<br>change.|



### **Important interaction rule** 

Showing an option is not necessarily the same as reserving it, and reserving it is not necessarily the same as confirming it. Students must define these meanings and what the driver sees at every stage. 

##### **9. · Operating Constraints Students Must Consider** 

#### **9.1 Slot feasibility** 

- The driver must be able to reach the facility before the receiving window begins. 

- The slot must fall within facility operating hours. 

- The dock must support the vehicle type and load requirements. 

- The unloading duration must fit the remaining capacity. 

- The facility may restrict carrier, product class, temperature control or appointment type. 

- Availability may change between viewing, discussing, requesting and confirming a slot. 

#### **9.2 Allocation policy** 

SetuHaul has not defined one universal allocation policy. Students must expose the trade-offs and propose a defensible policy rather than hiding the decision inside a prompt. 



For doubts reach out to: <u>delivery@fde.academy</u> 

13 





|**POSSIBLE CONSIDERATION**|**WHY IT MAY MATTER**|
|---|---|
|**First confirmed, first served**|Simple and predictable, but may ignore service criticality.|
|**Customer or shipment priority**|Protects important commitments but may appear unfair.|
|**Perishable or time-sensitive**<br>**goods**|Delay may create greater operational or product risk.|
|**Earliest feasible arrival**|May reduce waiting and improve dock utilisation.|
|**Driver duty time and next**<br>**assignment**|The driver may have limited operating time remaining.|
|**Fairness across carriers**|Prevents one carrier from repeatedly consuming scarce capacity.|
|**Warehouse utilisation and**<br>**overtime**|Some choices may create labour or equipment cost.|



#### **9.3 Human control** 

- Driver safety decisions remain with the driver, carrier and human operations team. 

- Commercial penalties, compensation and customer commitments require authorised approval. 

- No-feasible-slot cases must support escalation rather than inventing an answer. 

- Contradictory information, regulated loads and emergency situations require manual takeover. 

##### **10. · Core Data Package for Students** 

Provide the business truth required to understand and design the system, but do not pre-create solution-specific structures such as a slot-hold table, allocation-decision table or agent-actions table. Students should decide whether such structures are necessary. 

#### **10.1 Identity and movement data** 

|**TABLE**|**BUSINESS MEANING**|**IMPORTANT FIELDS**|
|---|---|---|
|**drivers**|The person using chat and their<br>carrier context.|driver_id, name, phone, carrier_id, status,<br>home_base|
|**vehicles**|The truck assigned to a movement<br>and its physical requirements.|vehicle_id, carrier_id, vehicle_type, length_ft,<br>refrigeration_required, status|
|**shipments**|The active freight movement<br>connecting driver, vehicle, origin<br>and destination.|shipment_id, driver_id, vehicle_id, origin_id,<br>destination_id, product_class, priority,|





For doubts reach out to: <u>delivery@fde.academy</u> 

14 





|**TABLE**|**BUSINESS MEANING**|**IMPORTANT FIELDS**|
|---|---|---|
|||planned_eta, expected_unload_minutes,<br>status|
|**eta_updates**|A history of revised ETAs explicitly<br>declared by the driver or operations<br>team. No live tracking is required.|eta_update_id, shipment_id, declared_eta,<br>source_type, declared_at, confidence_note|
|**facility_checkins**|Observed arrival and waiting state<br>once the truck reaches the<br>destination facility.|checkin_id, shipment_id, facility_id,<br>gate_in_at, arrival_status, queue_status,<br>dock_in_at, completed_at|



#### **10.2 Warehouse capacity data** 

|**TABLE**|**BUSINESS MEANING**|**IMPORTANT FIELDS**|
|---|---|---|
|**facilities**|Receiving sites and their operating<br>calendars.|facility_id, name, city, timezone, open_time,<br>close_time, contact_id|
|**docks**|Physical loading bays and<br>compatibility constraints.|dock_id, facility_id, dock_name,<br>supported_vehicle_type,<br>supported_product_class, active_flag|
|**appointment_slots**|Units of receiving time and capacity.|slot_id, facility_id, dock_id, start_time,<br>end_time, capacity_units, slot_status|
|**appointments**|The current or historical booking<br>connecting a shipment to a slot.|appointment_id, shipment_id, slot_id, status,<br>booked_at, confirmed_at, cancelled_at|
|**facility_rules**|Local rules that change eligibility or<br>operating behaviour.|rule_id, facility_id, rule_type, rule_value,<br>effective_from, effective_to|



#### **10.3 Exception and conversation data** 

|**TABLE**|**BUSINESS MEANING**|**IMPORTANT FIELDS**|
|---|---|---|
|**driver_exceptions**|Each disruption reported for a<br>shipment.|exception_id, driver_id, shipment_id,<br>exception_type, reported_delay_minutes,<br>latest_declared_eta, reported_at, status|
|**chat_messages**|The conversational record for the<br>exception thread.|message_id, thread_id, exception_id,<br>sender_type, message_text, created_at|





For doubts reach out to: <u>delivery@fde.academy</u> 

15 





|**TABLE**|**BUSINESS MEANING**|**IMPORTANT FIELDS**|
|---|---|---|
|**contacts**|Operational stakeholders who may|contact_id, party_type, name, email, phone,|
||need updates or approval.|facility_id, shipment_id|



#### **10.4 Optional enrichment data** 

|**TABLE**|**WHY IT HELPS**|
|---|---|
|**facility_capacity_changes**|Creates events such as a dock closure, equipment failure or reduced<br>labour.|
|**appointment_history**|Shows earlier reschedules, cancellations and changes made to the booked<br>plan.|
|**customer_commitments**|Adds service-level and priority context without exposing commercial detail.|
|**operational_messages**|Represents warehouse or customer replies outside the driver chat.|
|**scheduling_runs**|Optionally stores the input snapshot, proposed sequence, objective values<br>and explanation from a scheduling tool for later review.|



#### **10.5 What not to give students in advance** 

- A completed slot-allocation or scheduling algorithm. Students may design one, but it should not be supplied as the answer key. 

- A predefined agent tool list or orchestration graph. 

- A ready-made slot-hold or locking model. 

- A final priority policy. 

- A table that records the “correct” solution for each request. 

### **Why this matters** 

Students need enough data to understand the business, but the data model should not reveal the intended implementation. Their job is to discover what additional state, controls and interfaces are needed. 

##### **11. · How to Make the Dataset Realistic** 

#### **11.1 Recommended classroom size** 



For doubts reach out to: <u>delivery@fde.academy</u> 

16 





|**ENTITY**|**SUGGESTED VOLUME**|
|---|---|
|**Drivers**|80-120|
|**Vehicles**|90-140|
|**Shipments**|600-1,000 across seven days|
|**ETA updates**|800-1,500, including unchanged, corrected and uncertain<br>estimates|
|**Facility check-ins**|400-700 gate, yard, dock and completion events|
|**Facilities**|6|
|**Docks**|24-32|
|**Appointment slots**|2,000-3,000|
|**Appointments**|900-1,500|
|**Exceptions**|250-400|
|**Chat messages**|1,500-3,000|



#### **11.2 Required stress scenarios** 

- At least 10 drivers request alternatives for the same facility and evening window while only 3-4 compatible slots exist. 

- At the same time, one truck is early and waiting, one truck arrived late and is waiting, one truck is currently unloading, and another driver has declared a later ETA but has not yet arrived. 

- Two drivers select the same option within a few seconds. 

- One facility reduces capacity after options have already been discussed. 

- A cancellation creates a new slot during an active conversation. 

- A driver sends duplicate messages because of weak connectivity. 

- A driver has more than one shipment record, requiring disambiguation. 

- A stated 90-minute repair delay does not equal a 90-minute ETA shift. 

- One shipment has higher priority but enters the queue later. 

- One request has no feasible same-day slot. 

- A warehouse reply conflicts with the stored schedule. 

#### **11.3 Data imperfections** 

- Missing delay duration or uncertain repair completion time. 



For doubts reach out to: <u>delivery@fde.academy</u> 

17 





- Free-text location names and inconsistent spelling. 

- A stale latest-declared ETA, a missing ETA timestamp or several corrections within the same conversation. 

- Cancelled appointments still visible in history. 

- Facility rules effective only during part of the day. 

- Different descriptions for the same exception reason. 

##### **12. · Open-Ended Student Brief** 

Students are expected to design and demonstrate a credible solution to the business problem. The brief intentionally does not prescribe the architecture. 

#### **12.1 Questions students must answer** 

**1.** What information must be collected before useful options can be shown? 

**2.** How is a conversation connected to the correct driver, shipment and appointment? 

**3.** How is revised arrival time determined and uncertainty communicated? 

**4.** What makes a slot feasible for a specific shipment? 

**5.** What does “available” mean while another driver is considering the same slot? 

**6.** At what point does an option become a hold, request, reservation or confirmed booking? 

**7.** How are simultaneous requests ordered when capacity is insufficient? 

**8.** Optional scheduling extension: when should a facility-wide schedule be recalculated, which work is fixed, and what objective is being optimised? 

**9.** How are stale options, cancellations, duplicate messages and retries handled? 

**10.** What happens when there is no feasible slot? 

**11.** What is explained when the preferred slot is not granted? 

**12.** Which decisions require human approval or takeover? 

**13.** How will the team prove that the system did not double-book capacity? 

#### **12.2 Expected demonstration** 

- A driver reports a delay and answers one or more clarification questions. 

- The driver asks for later possibilities and compares alternatives. 

- Several requests are processed against the same facility schedule. 

- Optional: a scheduling tool receives the facility snapshot and proposes a revised sequence after an ETA update or gate check-in. 

- At least two requests compete for the same capacity. 

- The driver is shown what happens when an option changes or disappears. 

- At least one case ends in escalation because no safe or feasible automated outcome exists. 



For doubts reach out to: <u>delivery@fde.academy</u> 

18 





#### **12.3 Out of scope** 

- National transport-network optimisation; the optional extension is limited to dock scheduling within one facility or a small facility set. 

- Carrier selection and freight-rate negotiation 

- Autonomous driver-safety decisions 

- Customs, hazardous-material and legal-compliance workflows 

- Commercial penalty approval 

##### **13. · Business Success and Reference** 

#### **13.1 Business success definition** 

_Success is not “the chatbot answered.” Success means that a driver exception becomes a feasible, current and clearly communicated operating plan without creating a conflict for another driver._ 

|**MEASURE**|**WHAT IT REVEALS**|
|---|---|
|**Time from first message to usable**<br>**outcome**|Operational speed|
|**Share resolved without manual**<br>**takeover**|Automation coverage|
|**Conflicting or duplicate allocations**|Correctness under concurrency|
|**Options later found infeasible**|Freshness and decision quality|
|**No-feasible-slot escalations handled**<br>**correctly**|Safety of failure behaviour|
|**Average driver waiting after**<br>**rescheduling**|Operational outcome|
|**Warehouse slot utilisation**|Capacity efficiency|
|**Priority-policy violations**|Business-policy compliance|
|**Driver clarification turns**|Conversation effort and data completeness|



#### **13.2 Industry reference** 



For doubts reach out to: <u>delivery@fde.academy</u> 

19 





Opendock is a useful industry reference, not the answer key. Its public materials describe carrier self-scheduling, driver-to-facility communication, digital check-in and real-time appointment syncing. This validates the business category while leaving students to design their own classroom solution. 

### **Sources** 

**1.** American Transportation Research Institute (ATRI), "New Research Documents Substantial Financial and Safety Impacts from Truck Driver Detention," September 2024. 

**2.** Opendock, Dock Scheduling Software and Product Tours. 

**3.** Google OR-Tools, Scheduling Overview and The Job Shop Problem. 

**4.** R. N. Monemia and S. Gelareh, Dock Assignment and Truck Scheduling Problem; Consideration of Multiple Scenarios with Resource Allocation Constraints, 2023. 

**5.** R. Mahes, M. Mandjes, M. Boon and P. Taylor, Dynamic Appointment Scheduling, 2021. 

### **Final student challenge** 

Design a conversational freight-exception service that remains correct when several drivers ask for the same limited capacity at the same time. Optionally, add a facility-level scheduling tool that considers early, late, waiting and future-arriving trucks together. Explain not only what the system says, but how the business can trust the allocation and communication around it. 


# **Add-ons for the Project** 

_Two practical ways to make the core solution stronger_ 

## **Before you start** 

These are optional. First make sure the basic flow works: the driver reports a delay, the system finds the correct shipment, checks the appointment, and helps the driver choose a workable slot. Add the ideas below only after that flow is stable. 

#### **1. · Add location only when it helps** 

A driver may say, “I should reach by 7 PM.” That is useful, but it is still only an estimate. The driver may be guessing, traffic may have changed, or the message may have been sent some time ago. The optional improvement is simple: allow the driver to share the current location once. Use that location to calculate a route ETA and compare it with what the driver said. This is not continuous tracking. It is only a location snapshot shared during the conversation. 

## **What students are trying to achieve** 

Use the location to make the slot suggestion more sensible. Do not add a map feature just for display. The location should change the ETA, the arrival buffer, or the recommended slot. 

## **A simple example** 

|**INFORMATION**|**VALUE**|
|---|---|
|**Current appointment**|6:00 PM|
|**Driver says**|“I should reach by 6:30 PM.”|
|**Location-based ETA**|6:45 PM|
|**Available option 1**|7:00 PM — only 15 minutes of buffer|
|**Available option 2**|7:30 PM — 45 minutes of buffer|



## **A useful answer would be:** 

## **Example agent response** 



For doubts reach out to: <u>delivery@fde.academy</u> 

1 





_“Based on the location you shared, your expected arrival is around 6:45 PM. The 7:00 PM slot is possible, but it leaves only 15 minutes of buffer. The 7:30 PM slot is safer. Which one would you like to choose?”_ 

### **How the application can request browser location** 

The Python agent or backend cannot directly read the driver’s browser location. The conversation should first ask for permission. When the driver agrees, the application should pause the current workflow, ask the frontend to collect one location snapshot, and resume only after the browser returns a result. 

## **Suggested interaction pattern** 

**1.** The assistant asks: “Would you like to share your current location?” 

**2.** If the driver agrees, return a client action such as REQUEST_BROWSER_LOCATION and mark the case as waiting for browser input. 

**3.** The frontend shows a Share location button. Only the user click should trigger the browser permission request. 

**4.** The browser returns latitude, longitude, accuracy and capture time, or a denied/error result. 

**5.** The frontend sends the result to the backend. The saved conversation or case then continues from the same point. 

**6.** If the driver declines or location fails, continue using the driver-declared ETA. 

_Design freedom: students may use their own pending-action state, a framework interrupt, or another human-in-the-loop pattern. The required outcome is that the workflow waits safely for browser input._ 

_Illustrative chat and browser permission flow. The exact browser prompt will vary by device and browser._ 

### **Suggested routing service: Geoapify** 

After receiving the coordinates, the backend can call the Geoapify Routing API with the truck’s current location and the destination facility coordinates. The API can return route distance and estimated travel time for 

truck-related routing modes. The application should calculate and store the resulting route ETA, the provider and the calculation time. 

_Reference: Geoapify Routing API documentation_ 

_Browser note: a deployed application normally uses navigator.geolocation.getCurrentPosition() after the driver clicks the button. The browser asks for explicit permission and the application generally needs to run over HTTPS. Use a one-time location snapshot, not continuous tracking._ 

### **What needs to be built** 

- Ask the driver whether they want to share a one-time browser location. Location sharing must remain optional. 

- When the driver agrees, pause or interrupt the current workflow and return a frontend action such as REQUEST_BROWSER_LOCATION. The backend tool itself cannot open the browser permission prompt. 



For doubts reach out to: <u>delivery@fde.academy</u> 

2 





- The frontend should call the browser geolocation capability only after the driver clicks Share location, then send latitude, longitude, accuracy and capture time back to the backend. 

- Use the Geoapify Routing API to calculate route distance and travel time from the shared coordinates to the destination facility. Use an appropriate truck routing mode. 

- Keep the driver-declared ETA and route-based ETA separately. Do not overwrite one with the other. 

- Use the ETA and arrival buffer to rank or explain slot options. 

- If location is denied, unavailable or stale, continue with the normal driver-declared ETA workflow. 

## **Data to keep** 

|**DATA**|**WHY IT MATTERS**|
|---|---|
|**Shared location and time**|A location sent 30 minutes ago may no longer be useful.|
|**Driver-declared ETA**|Shows what the driver believes.|
|**Route-based ETA**|Shows what the map or route service calculated.|
|**ETA source used for scheduling**|Lets us later check whether the choice was sensible.|
|**Actual gate-in time**|Used to see which ETA was closest to reality.|



## **Cases students should test** 

- The driver shares an ETA but no location. 

- The driver shares location but gives no ETA. 

- The driver ETA and route ETA are almost the same. 

- The two ETAs differ by a large amount. 

- The shared location is old. 

- The location service fails or times out. 

- The driver shares another location later and the ETA changes. 

- The truck has already reached the gate, so actual gate-in becomes the latest truth. 

- The driver does not want to share location. The normal workflow must still continue. 

#### **2. · Show whether the solution actually helped** 

A working demo is not enough. The final presentation should answer a few simple business questions: Did the system give a better ETA? Did the driver get a usable slot faster? Did fewer cases need a person from operations? Did the recommended slot reduce the risk of extra waiting? 



For doubts reach out to: <u>delivery@fde.academy</u> 

3 





The aim is not to create a large analytics platform. A few well-chosen measures are enough, as long as they come from the actual workflow. 

## **What to measure** 

|**MEASURE**|**WHAT IT MEANS AND HOW TO CHECK IT**|
|---|---|
|**Time to resolve the case**|Time from the first driver message to a confirmed or usable plan.|
|**Human help needed**|Share of cases where an operations executive had to step in.|
|**Self-service rescheduling**|Share of driver requests completed without operations taking over.|
|**ETA error**|Difference between the ETA used by the system and the actual gate-in<br>time.|
|**First option accepted**|How often the driver accepted the first recommended slot.|
|**Estimated waiting reduced**|Expected wait under the old plan minus expected wait after the chosen<br>slot.|



## **A simple before-and-after view** 

Students can use historical data or a controlled test set. The comparison should be fair: use similar facilities, similar types of delay, and the same definition for each measure. 

|**QUESTION**|**MANUAL PROCESS**|**WITH THE SOLUTION**|
|---|---|---|
|How long did resolution take?|Example: 18 minutes|Example: 7 minutes|
|How many cases needed<br>operations?|Example: 7 out of 10|Example: 3 out of 10|
|How accurate was the ETA?|Example: 29-minute error|Example: 17-minute error|



_The values above are only examples. Students must calculate their own results from the data they generate or process._ 

### **Where LangSmith and CloudWatch fit** 

|**TOOL**|**USE IT TO ANSWER**|
|---|---|
|**LangSmith**|What did the agent understand? Which tools did it call? Did it recommend only the<br>slots returned by the scheduling tool? How many questions did it ask?|
|**CloudWatch or**|Was the application slow? Did the location service fail? How long did scheduling|
|**application logs**|take? How many cases were completed, failed, or sent to a human?|





For doubts reach out to: <u>delivery@fde.academy</u> 

4 





_Keep the setup small. A few useful traces and metrics are better than a dashboard full of numbers that do not lead to any action._ 

### **Minimum data needed for measurement** 

|**DATA TO STORE**|**WHY IT IS NEEDED**|
|---|---|
|**Case start and resolution time**|Shows how long the full exception took to resolve.|
|**Time when options were generated**|Shows how long the system took to produce useful choices.|
|**Human intervention required**|Shows whether operations had to take over.|
|**ETA source used**|Shows whether the system relied on the driver, location service, or<br>another source.|
|**Predicted ETA and actual gate-in**<br>**time**|Lets the team calculate ETA error.|
|**Old and new projected waiting time**|Lets the team estimate whether the recommendation reduced<br>waiting.|



### **What students should show in the final demo** 

- One case where location clearly improves the ETA or slot choice. 

- One case where location is missing or fails, but the normal workflow still works. 

- The original ETA, driver ETA, route ETA, and actual gate-in time for a few shipments. 

- A small comparison of resolution time and human involvement before and after the solution. 

- One LangSmith trace showing the agent and tool flow, plus a small CloudWatch view or application log summary showing latency, failures, and completed cases. 

## **The final question** 

Did the location feature help the system make a better recommendation, and can the team show that the overall workflow became faster, more accurate, or less dependent on manual coordination? 

