# USER TESTING SESSION CHECKLIST

**Date:** ******\_\_\_\_****** **Time:** ******\_\_\_\_******

**Testers Present:** ☐ Nada ☐ Douaa ☐ Both

---

## PRE-SESSION SETUP

### Technical Setup

- [ ] ws_server.py running on Nada's laptop
  - Command: `python edge/ws_server.py`
  - Confirm: Server log shows "Server ready - ws://..."

- [ ] ngrok tunnel active (if remote testing)
  - Command: `ngrok http 8000`
  - URL shared: **************\_\_\_\_**************

- [ ] Connection test passed
  - Quick ping/pong or test connection verified
  - No firewall warnings

### Camera & Environment

- [ ] Camera positioned 2-3 meters from exercise area
- [ ] Full body visible in frame (head to feet)
- [ ] Good lighting - no shadows on user
- [ ] Background is clear/uncluttered
- [ ] Floor is non-slip and stable

### User Preparation

- [ ] User briefed on exercise (squats)
- [ ] Proper form demonstrated
- [ ] Test protocol explained (2 sets × 10 reps)
- [ ] User comfortable with being recorded
- [ ] User information collected:
  - Name/Initials: **************\_\_\_\_**************
  - Height (cm): ****\_\_****
  - Age: ****\_\_****

---

## TESTING COMMAND

```bash
python user_testing.py --user "______" --height ___ --age ___ --sets 2 --reps 10
```

**For remote (ngrok):**

```bash
python user_testing.py --user "______" --height ___ --age ___ \
  --host ______________.ngrok-free.dev --port 443 --ssl
```

---

## DURING SESSION MONITORING

### Set 1

- [ ] User comfortable and ready
- [ ] Press ENTER to start
- [ ] User performs 10 squats
- [ ] Monitor real-time display:
  - Reps counting correctly: ☐ Yes ☐ No
  - Latency < 100ms: ☐ Yes ☐ No
  - Landmarks detected: ☐ Yes ☐ No

**Manual Observation:**

- Form quality: ☐ Excellent ☐ Good ☐ Needs improvement
- Issues noted: **********************\_\_\_**********************

### Set 2

- [ ] Rest period (1-2 minutes)
- [ ] User ready for Set 2
- [ ] Press ENTER to start
- [ ] User performs 10 squats
- [ ] Monitor real-time display:
  - Reps counting correctly: ☐ Yes ☐ No
  - Latency < 100ms: ☐ Yes ☐ No
  - Landmarks detected: ☐ Yes ☐ No

**Manual Observation:**

- Form quality: ☐ Excellent ☐ Good ☐ Needs improvement
- Issues noted: **********************\_\_\_**********************

---

## POST-SESSION

- [ ] Review generated report on screen
- [ ] JSON file saved: user_test****\_\_\_****.json
- [ ] User debriefing:
  - Did the system feel responsive? ☐ Yes ☐ No
  - Did rep counting seem accurate? ☐ Yes ☐ No
  - Any lag or delay noticed? ☐ Yes ☐ No
  - Comments: **********************\_**********************

---

## QUICK METRICS (from report)

### Set 1

- Actual reps: **\_\_**
- Counted reps: **\_\_**
- Accuracy: **\_\_**%
- Mean latency: **\_\_** ms
- Max latency: **\_\_** ms

### Set 2

- Actual reps: **\_\_**
- Counted reps: **\_\_**
- Accuracy: **\_\_**%
- Mean latency: **\_\_** ms
- Max latency: **\_\_** ms

### Overall

- Rep accuracy: **\_\_**% (Target: ≥90%)
- Avg latency: **\_\_** ms (Target: <100ms)
- **Meets targets:** ☐ YES ☐ NO

---

## TROUBLESHOOTING NOTES

If issues occurred, document here:

- Problem: ************************\_\_\_************************
- When: **************************\_**************************
- Resolution: **********************\_\_\_\_**********************

---

## USERS TESTED (Track Progress)

| User # | Name | Date | Accuracy | Latency | Status |
| ------ | ---- | ---- | -------- | ------- | ------ |
| 1      |      |      |          |         | ☐      |
| 2      |      |      |          |         | ☐      |
| 3      |      |      |          |         | ☐      |

**Target: Test 3 users before final demo**

---

## FINAL READINESS CHECK

After testing all 3 users:

Run: `python testing_summary.py user_test_*.json`

- [ ] Average accuracy across all users ≥90%
- [ ] Average latency across all users <100ms
- [ ] All 3 users tested
- [ ] No critical issues identified

**READY FOR FINAL DEMO:** ☐ YES ☐ NO

**If NO, actions needed:**

- ***
- ***

---

**Session completed by:** ******\_\_\_\_****** **Signature:** ******\_\_\_\_******
