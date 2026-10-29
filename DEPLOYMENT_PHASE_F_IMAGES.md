# CVScreen Master Deployment — Phase F: Container Image Verification

**Document:** `DEPLOYMENT_PHASE_F_IMAGES.md`  
**Execution Date:** October 16, 2026  
**Role:** Senior DevOps & AI Infrastructure Engineer  
**Status:** Both Images Verified and Ready in ACR  
**Registry:** `crcvscreenexample.azurecr.io`  

---

## 1. Backend Image Verification

- **Repository:** `cvscreening-backend`
- **Active Tags:** `latest`, `v2-durable`
- **Manifest Index Digest:** `sha256:41a30b9ac2ffdb339452a9b02825a1d1183fc7221cc1ccc189ba30d6cc504e00`
- **Linux/AMD64 Manifest Digest:** `sha256:feba177c22ab8febe18a04b0c97c6b0815863e01e77135bdb900f7844d319103`
- **OS / Architecture:** `linux/amd64`
- **Pre-baked AI Model:** Qwen 2.5 1.5B via Ollama daemon (`/app/entrypoint.sh` startup verified offline)
- **Database Durability:** Online SQLite backup API with transactional integrity checks and `SIGTERM` trap for zero-data-loss shutdown.

---

## 2. Frontend Image Verification

- **Repository:** `cvscreening-frontend`
- **Active Tag:** `latest`
- **Manifest Index Digest:** `sha256:7b861ff9afb7d3c40e402abfd7d99faef70821fd35e255381b1147eeab657392`
- **Linux/AMD64 Manifest Digest:** `sha256:1b9e6ca20d035eba4cb3c2c450bb1f2dea0cce0d087a6a3d0ffd7f88e3918736`
- **OS / Architecture:** `linux/amd64`
- **Payload:** React 19 SPA + Nginx reverse proxy routing `/api/*` to internal backend with 300s timeout.

---

## 3. Phase F Conclusion

Both backend and frontend images are verified, linux/amd64 compliant, and available in the private ACR.
