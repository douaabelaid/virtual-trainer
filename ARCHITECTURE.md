# Production Architecture — Virtual Trainer

## Architecture Overview

Le système Virtual Trainer utilise une architecture **3-tier** avec séparation claire des responsabilités pour optimiser les performances temps réel et la scalabilité.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PRODUCTION ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   FRONTEND   │◄───────►│     EDGE     │◄───────►│   BACKEND    │
│   (Mobile)   │  WebSocket   (Jetson)  │   HTTP   │     API      │
│              │         │              │         │              │
│  React Native│         │  MediaPipe   │         │  Exercise    │
│  Camera API  │         │  Pose Det.   │         │  Logic + ML  │
│  WebGL/Canvas│         │  WebSocket   │         │  Database    │
│  Audio Player│         │  Audio Fwd   │         │  Analytics   │
└──────────────┘         └──────────────┘         └──────────────┘
      │                        │                        │
      │                        │                        │
      ▼                        ▼                        ▼
  User Device             Edge Device            Cloud/Server
  (Phone/Tablet)          (Jetson Nano)        (AWS/Azure/GCP)
```

---

## 🎯 Separation of Responsibilities

### 1. **FRONTEND (Mobile App)**

**Rôle:** Interface utilisateur et capture de données

**Responsabilités:**
- ✅ Capture vidéo (caméra native)
- ✅ Affichage temps réel (pose skeleton overlay)
- ✅ Lecture audio feedback
- ✅ UI/UX (compteur de reps, timer, scores)
- ✅ Gestion session utilisateur
- ✅ Cache local et mode offline

**Technologies:**
- React Native / Flutter
- WebSocket client
- Canvas/WebGL pour rendering
- Native camera APIs

**Ce que le frontend NE fait PAS:**
- ❌ Détection de pose (trop lourd, batterie)
- ❌ Logique d'exercice (complexe, nécessite mise à jour fréquente)
- ❌ Calculs d'angles (déporté à l'edge/backend)
- ❌ Génération TTS (trop de ressources)

---

### 2. **EDGE (Jetson Nano / Edge Server)**

**Rôle:** Traitement temps réel low-latency

**Responsabilités:**
- ✅ **Pose Detection** — MediaPipe inference (GPU acceleration)
- ✅ **Frame processing** — 15-30 FPS avec latence < 100ms
- ✅ **WebSocket server** — Communication bidirectionnelle avec mobile
- ✅ **Audio forwarding** — Streaming audio du backend vers mobile
- ✅ **Latency optimization** — Frame skip, buffering, throttling
- ✅ **Multi-client handling** — Plusieurs utilisateurs simultanés

**Pourquoi l'edge est critique:**

#### ⚡ **1. Latence réseau**
```
Sans Edge:
Mobile → Cloud Backend (MediaPipe) → Mobile
Latency: 150-300ms (RTT réseau + inference)
Result: Lag visible, mauvaise UX

Avec Edge:
Mobile → Edge locale (MediaPipe) → Mobile
Latency: 20-60ms (LAN + inference)
Result: Temps réel fluide
```

#### 🔋 **2. Économie batterie mobile**
```
MediaPipe sur mobile:
- CPU/GPU à 100% pour inference
- Batterie drainée en 30-45 minutes
- Chauffe excessive du téléphone

MediaPipe sur edge:
- Mobile utilise seulement caméra + réseau
- Batterie dure 2-3 heures
- Téléphone reste cool
```

#### 🌐 **3. Scalabilité**
```
1 Jetson Nano peut servir:
- 5-10 utilisateurs simultanés
- Chacun avec 15-30 FPS
- Dans un gym local (LAN)

Sans edge, chaque utilisateur:
- Consomme ressources cloud
- Coûts serveur × nombre d'utilisateurs
- Dépendance internet obligatoire
```

#### 🏠 **4. Scénarios de déploiement**

**Scénario A: Gym/Studio de Fitness**
```
┌─────────────────────────────────────────┐
│         Réseau Local Gym (LAN)          │
│                                         │
│  📱 Client 1 ┐                         │
│  📱 Client 2 ├──► 🖥️  Jetson Nano     │
│  📱 Client 3 │      (Edge Server)      │
│  📱 Client 4 ┘           │              │
│                          │              │
└──────────────────────────┼──────────────┘
                           │ Internet
                           ▼
                    ☁️  Backend API
                    (Exercise logic, analytics)
```

**Avantages:**
- Latence ultra-faible (< 30ms)
- Pas de dépendance Internet pour pose detection
- Coûts cloud réduits
- Données sensibles restent locales

**Scénario B: Usage Mobile (sans Edge)**
```
📱 Mobile App ──► ☁️ Cloud Backend (MediaPipe + Logic)
                   
Latency: 150-300ms
Coût: $$$ (GPU cloud instances)
Offline: ❌ Non possible
```

**Scénario C: Hybrid (Edge + Cloud)**
```
📱 Mobile ──► 🖥️ Jetson (Pose) ──► ☁️ Backend (Logic)
              20-60ms              50-100ms
              
Latency totale: 70-160ms
Coût: $ (Edge one-time + cloud léger)
Offline: ✅ Pose detection fonctionne
```

---

### 3. **BACKEND (Cloud API)**

**Rôle:** Logique métier et persistance

**Responsabilités:**
- ✅ **Exercise logic** — Rules, rep counting, form analysis
- ✅ **Feedback generation** — Determine quoi dire à l'utilisateur
- ✅ **TTS synthesis** — Génération audio coaching
- ✅ **Analytics** — Tracking progression, statistiques
- ✅ **User management** — Comptes, authentification, profils
- ✅ **Database** — Historique workouts, scores
- ✅ **ML models** — Form classification avancée (optionnel)

**Technologies:**
- FastAPI / Django / Node.js
- PostgreSQL / MongoDB
- TTS engine (Coqui, Google Cloud TTS)
- ML frameworks (PyTorch, TensorFlow)

**Pourquoi séparer backend de edge:**

#### 🔄 **1. Évolutivité rapide**
```
Modifier logique d'exercice:
- Backend: Deploy nouveau code → instantané
- Edge: Nécessite update firmware Jetson → lent

Ajouter nouveau exercice:
- Backend: Ajouter règles → quelques minutes
- Edge: Modifier MediaPipe model → impossible/complexe
```

#### 💾 **2. Persistance et Analytics**
```
Backend gère:
- Historique de tous les workouts
- Comparaisons inter-utilisateurs
- Recommendations personnalisées
- Rapports de progression

Edge ne peut pas:
- Stocker données long-terme (mémoire limitée)
- Faire analytics complexes (CPU limité)
- Corréler données multi-utilisateurs
```

#### 🧠 **3. Intelligence avancée**
```
Backend peut:
- ML models lourds (form classification)
- Computer vision secondaire (depth estimation)
- Correlation avec biométrie (heart rate, etc.)

Edge limite:
- Doit rester light pour temps réel
- Priorité = vitesse pas précision max
```

---

## 📊 Data Flow — Production

### Flow 1: Real-time Pose Tracking (15-30 FPS)

```
┌─────────────┐
│   MOBILE    │
└─────────────┘
      │
      │ 1. Capture frame (camera)
      │    RGB 640×480 @ 30 FPS
      │
      ▼
┌─────────────┐
│   Encode    │ 2. JPEG compression + Base64
│   + Send    │    Size: ~15-30 KB/frame
└─────────────┘
      │
      │ 3. WebSocket (binary/text)
      │    Protocol: ws:// or wss://
      │    Latency: 5-20ms (LAN) or 50-150ms (Internet)
      │
      ▼
┌─────────────────────────────────────┐
│          EDGE (Jetson)              │
│                                     │
│  ┌──────────────────────────┐      │
│  │ 4. Receive + Decode      │      │
│  │    Base64 → JPEG → RGB   │      │
│  └──────────┬───────────────┘      │
│             │                       │
│             ▼                       │
│  ┌──────────────────────────┐      │
│  │ 5. MediaPipe Inference   │      │
│  │    GPU acceleration      │      │
│  │    Latency: 15-30ms      │      │
│  │    Output: 33 landmarks  │      │
│  └──────────┬───────────────┘      │
│             │                       │
│             ▼                       │
│  ┌──────────────────────────┐      │
│  │ 6. Validate + Format     │      │
│  │    MediaPipe names       │      │
│  │    JSON serialization    │      │
│  └──────────┬───────────────┘      │
│             │                       │
└─────────────┼───────────────────────┘
              │
              │ 7. Send landmarks (JSON)
              │    Size: ~2-5 KB
              │    WebSocket
              │
              ▼
┌─────────────────────────┐
│       MOBILE            │
│                         │
│  8. Render skeleton     │
│     Canvas/WebGL        │
│     Latency: 1-5ms      │
│                         │
│  Total E2E: 40-100ms    │
└─────────────────────────┘
```

**Total Latency Budget:**
```
Component               | Latency (LAN) | Latency (Internet)
------------------------|---------------|-------------------
1. Camera capture       | 33ms (30FPS)  | 33ms
2. JPEG encode          | 5ms           | 5ms
3. Network (Mobile→Edge)| 5-10ms        | 50-100ms
4. Decode               | 2ms           | 2ms
5. MediaPipe inference  | 15-30ms       | 15-30ms
6. Validate/format      | 1ms           | 1ms
7. Network (Edge→Mobile)| 5-10ms        | 50-100ms
8. Render               | 2ms           | 2ms
------------------------|---------------|-------------------
TOTAL                   | 68-93ms ✅    | 158-273ms ⚠️
```

---

### Flow 2: Exercise Analysis + Feedback (Async, < 1 Hz)

```
┌─────────────┐
│   MOBILE    │
└─────────────┘
      │
      │ Real-time landmarks stream
      │ (from Flow 1)
      │
      ▼
┌──────────────────────┐
│    EDGE (Jetson)     │
│                      │
│  1. Buffer last 30   │
│     landmarks        │
│     (1 second @30FPS)│
└──────────┬───────────┘
           │
           │ 2. Send batch to Backend
           │    HTTP POST /analyze
           │    JSON payload: landmarks + metadata
           │    Frequency: 1-2 Hz (not every frame!)
           │
           ▼
┌─────────────────────────────────────────┐
│         BACKEND API (Cloud)             │
│                                         │
│  ┌──────────────────────────┐          │
│  │ 3. Exercise Logic        │          │
│  │    - Angle calculation   │          │
│  │    - Rep counting        │          │
│  │    - Form analysis       │          │
│  │    Latency: 10-50ms      │          │
│  └──────────┬───────────────┘          │
│             │                           │
│             ▼                           │
│  ┌──────────────────────────┐          │
│  │ 4. Feedback Decision     │          │
│  │    - Detect issues       │          │
│  │    - Priority/severity   │          │
│  │    Latency: 5ms          │          │
│  └──────────┬───────────────┘          │
│             │                           │
│             ▼                           │
│  ┌──────────────────────────┐          │
│  │ 5. TTS Synthesis         │          │
│  │    - Generate audio      │          │
│  │    - Cache common clips  │          │
│  │    Latency: 50-200ms     │          │
│  └──────────┬───────────────┘          │
│             │                           │
└─────────────┼───────────────────────────┘
              │
              │ 6. Send audio + metadata
              │    HTTP Response or WebSocket
              │    Payload: base64 WAV + feedback code
              │
              ▼
┌──────────────────────┐
│    EDGE (Jetson)     │
│                      │
│  7. Receive audio    │
│     Check cooldown   │
│     (prevent spam)   │
└──────────┬───────────┘
           │
           │ 8. Forward to mobile
           │    WebSocket binary frame
           │    Audio metadata (JSON) + WAV data
           │
           ▼
┌─────────────────────────┐
│       MOBILE            │
│                         │
│  9. Play audio          │
│     Native audio API    │
│     Latency: 10-50ms    │
│                         │
│  Total: 200-500ms ✅    │
│  (acceptable, not       │
│   real-time critical)   │
└─────────────────────────┘
```

**Latency acceptable car:**
- Feedback audio n'est pas frame-by-frame
- 200-500ms imperceptible pour coaching vocal
- Important: pose visualization reste temps réel (Flow 1)

---

## 🎛️ Real-Time Constraints

### Critical Path (Must be < 100ms)

**Pose Visualization:**
```
Mobile Camera → Edge MediaPipe → Mobile Display
Target: < 100ms E2E
Actual: 40-100ms ✅

Contrainte: Doit suivre mouvement en temps réel
Impact si dépassé: Lag visible, UX dégradée
```

**Optimisations:**
- Frame skip si latence > 100ms (edge)
- Throttling à 15 FPS (évite surcharge)
- Binary WebSocket frames (pas JSON pour images)
- GPU acceleration sur Jetson

### Semi-Real-Time (Can be 200-500ms)

**Audio Feedback:**
```
Backend Analysis → TTS → Edge → Mobile Play
Target: < 500ms
Actual: 200-500ms ✅

Contrainte: Feedback rapide mais pas frame-sync
Impact si dépassé: Coaching légèrement retardé (acceptable)
```

**Optimisations:**
- TTS cache (clips pré-générés)
- Cooldown 500ms (évite spam)
- Async processing (ne bloque pas pose)

### Non-Real-Time (Can be > 1s)

**Analytics & Database:**
```
Workout Summary → Database → Analytics Dashboard
Target: < 5s
Actual: 1-5s ✅

Contrainte: Batch processing OK
Impact si dépassé: Stats mises à jour lentement (OK)
```

---

## 🏗️ Deployment Scenarios

### Scenario 1: **Local Gym/Studio (Recommended)**

```
Topology:
  - 1× Jetson Nano (Edge server)
  - 5-10× Mobile clients (LAN WiFi)
  - 1× Internet connection (Backend)

┌────────────────────────────────────┐
│         Local Network (Gym)        │
│                                    │
│  📱 📱 📱 📱 📱                    │
│   ↓  ↓  ↓  ↓  ↓                   │
│  🖥️ Jetson Nano (192.168.1.100)  │
│       ↓                            │
│    Router ────► Internet           │
│                  ↓                 │
└──────────────────┼─────────────────┘
                   ▼
            ☁️ Backend API
         (analytics + logic)
```

**Avantages:**
- ✅ Ultra low latency (< 50ms)
- ✅ Fonctionne hors ligne pour pose detection
- ✅ Coût one-time (Jetson ~$99)
- ✅ Privacy (données restent locales)
- ✅ Scalable (1 Jetson = 10 users)

**Use case:**
- Gym avec 5-20 membres simultanés
- Studio de CrossFit, Pilates, Yoga
- Centre de physiothérapie

---

### Scenario 2: **Cloud-Only (No Edge)**

```
Topology:
  - Mobile apps partout dans le monde
  - Backend cloud avec MediaPipe

📱 User 1 (Paris) ──┐
📱 User 2 (Tokyo) ──┼──► ☁️ Backend (AWS us-east-1)
📱 User 3 (NYC)   ──┘    MediaPipe + Exercise Logic
```

**Avantages:**
- ✅ Pas de hardware edge à gérer
- ✅ Accessible partout (juste Internet)
- ✅ Scaling automatique (cloud elasticity)

**Inconvénients:**
- ❌ Latence élevée (150-300ms)
- ❌ Coûts cloud élevés (GPU instances)
- ❌ Batterie mobile drainée (si local inference)
- ❌ Dépendance Internet obligatoire

**Use case:**
- MVP / Beta testing
- Low user count (< 100 concurrent)
- Budget cloud important

---

### Scenario 3: **Hybrid (Edge + Cloud) — PRODUCTION**

```
Topology:
  - Edge for pose detection (low latency)
  - Backend for logic + analytics (scalable)

┌─────────────────┐         ┌──────────────────┐
│   Mobile App    │         │  Backend Cloud   │
└────────┬────────┘         └────────┬─────────┘
         │                           │
         │ Pose stream               │ Logic + Analytics
         │ 30 FPS                    │ 1-2 Hz
         │                           │
         ▼                           ▼
┌──────────────────────────────────────┐
│      Edge Server (Jetson)            │
│  - MediaPipe (real-time)             │
│  - WebSocket server                  │
│  - Audio forwarding                  │
└──────────────────────────────────────┘
```

**Data Flow:**
1. Mobile → Edge: Frames (30 FPS, WebSocket)
2. Edge → Mobile: Landmarks (30 FPS, WebSocket)
3. Edge → Backend: Landmark batches (1 Hz, HTTP)
4. Backend → Edge: Audio feedback (async, WebSocket)
5. Edge → Mobile: Audio stream (binary frames)

**Avantages:**
- ✅ Best of both worlds
- ✅ Low latency pose (< 50ms)
- ✅ Scalable logic (cloud backend)
- ✅ Coût optimisé (edge one-time, cloud léger)
- ✅ Works offline (pose only)

**Use case:**
- **Production recommandée**
- Gyms avec multiple locations
- SaaS fitness platform

---

## 💰 Cost Comparison

### Edge vs Cloud MediaPipe

**Option A: Edge (Jetson Nano)**
```
Hardware: $99 (one-time)
Power: ~10W × $0.12/kWh × 24h × 30d = $8.64/month
Internet: $50/month (gym already has)
Backend: $20/month (lightweight, just logic)
────────────────────────────────────
Total Month 1: $177.64
Total Month 12: $365 (~$30/month amortized)

Capacity: 5-10 concurrent users
Cost per user: $3-6/month
```

**Option B: Cloud GPU (AWS p3.2xlarge)**
```
Instance: $3.06/hour = $2,203/month (24/7)
OR
On-demand (8h/day): $734/month

Backend: Included (same instance)
────────────────────────────────────
Total: $734-2,203/month

Capacity: 10-20 concurrent users
Cost per user: $37-220/month
```

**Conclusion:**
- Edge = **10-50× cheaper** at scale
- Cloud = Better for MVP / low volume

---

## 🔐 Security & Privacy

### Edge Benefits

**Data Privacy:**
```
Edge processing:
- Video frames jamais envoyées au cloud
- Landmarks anonymes (pas d'image)
- RGPD compliant (données locales)

Cloud processing:
- Toutes les vidéos transitent par cloud
- Potentiel data leak
- Compliance complexe
```

**Network Security:**
```
Edge:
- LAN communication (pas exposé Internet)
- WebSocket avec TLS optionnel
- Attack surface réduite

Cloud:
- Tout sur Internet
- DDoS vulnerability
- Requires strong auth/firewall
```

---

## 📱 Mobile App: Edge vs No-Edge

### Question: "Le folder edge est-il uniquement pour Jetson, pas d'avantage pour mobile?"

**Réponse: L'edge apporte énormément d'avantages au mobile!**

### Avec Edge (Architecture actuelle)

**Mobile App est LÉGER:**
```javascript
// Mobile app responsibility
function captureAndSend() {
  const frame = camera.capture();
  const jpeg = frame.toJPEG({ quality: 0.7 });
  const b64 = jpeg.toBase64();
  
  websocket.send({
    type: "frame",
    data: b64
  });
}

// Receive processed landmarks
websocket.onmessage = (msg) => {
  const { landmarks } = JSON.parse(msg);
  renderSkeleton(landmarks);  // Simple canvas drawing
};
```

**Avantages mobile:**
- ✅ Batterie dure 2-3 heures (caméra + réseau seulement)
- ✅ CPU idle at 20-30%
- ✅ Pas de chauffe
- ✅ Fonctionne sur téléphones low-end
- ✅ App size: ~15 MB (pas de ML models)

### Sans Edge (MediaPipe sur mobile)

**Mobile App est LOURD:**
```javascript
// Mobile doit faire MediaPipe inference
import * as mediapipe from '@mediapipe/pose';

function processFrame() {
  const frame = camera.capture();
  
  // Heavy computation on mobile CPU/GPU!
  const results = await mediapipe.detectPose(frame);
  
  renderSkeleton(results.landmarks);
}
```

**Inconvénients mobile:**
- ❌ Batterie drainée en 30-45 min
- ❌ CPU/GPU à 100% continu
- ❌ Téléphone chauffe énormément
- ❌ Nécessite flagship phone (iPhone 13+, Galaxy S21+)
- ❌ App size: 50-100 MB (ML models inclus)
- ❌ Lag sur téléphones mid-range

---

## 🎓 Conclusion: Pourquoi Edge?

### L'edge n'est PAS optionnel

**C'est une nécessité pour:**

1. **Performance** — Sub-100ms latency impossible sans edge local
2. **User Experience** — Lag = users quit app
3. **Battery Life** — 3h vs 30min fait ÉNORME différence
4. **Accessibility** — Support téléphones low-end
5. **Cost** — 10-50× moins cher que cloud GPU
6. **Privacy** — Données vidéo restent locales
7. **Reliability** — Fonctionne hors ligne (mode dégradé)

### L'edge N'EST PAS:

- ❌ Juste pour Jetson (concept général edge computing)
- ❌ Remplaçable par mobile processing (trop lourd)
- ❌ Remplaçable par cloud (trop de latence)

### Architecture Recommandée

```
Production = Edge (Jetson) + Backend (Cloud) + Frontend (Mobile)

Chacun fait ce qu'il fait le mieux:
- Mobile: UI/UX
- Edge: Real-time ML inference
- Backend: Logic + Analytics
```

---

**TL;DR:**

| Component | Role | Can't be replaced by |
|-----------|------|---------------------|
| **Mobile** | UI, capture, display | ❌ Cloud (latency), ❌ Edge (no screen) |
| **Edge** | MediaPipe inference | ❌ Mobile (battery), ❌ Cloud (latency) |
| **Backend** | Logic, TTS, analytics | ❌ Edge (no scale), ❌ Mobile (no power) |

**Tous les trois sont nécessaires pour une architecture optimale!**
