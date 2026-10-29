import sys
import asyncio
import json
import time
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.config import settings, SAMPLES_DIR, EXTRACTED_DIR
from backend.app.agents.cv_agent import CVExtractionAgent
from backend.app.schemas.candidate import CandidateExtraction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Phase1Test")

async def run_phase1_tests():
    logger.info(f"Starting Phase 1 Test Suite using Ollama model: {settings.OLLAMA_LLM_MODEL}")
    logger.info(f"OLLAMA_BASE_URL: {settings.OLLAMA_BASE_URL}")

    sample_files = sorted(list(SAMPLES_DIR.glob("*.txt")))
    if not sample_files:
        logger.error(f"No sample CV files found in {SAMPLES_DIR}")
        return

    agent = CVExtractionAgent()
    results = []

    print("\n" + "=" * 85)
    print(f"  PHASE 1: OLLAMA CV EXTRACTION VERIFICATION ({len(sample_files)} SAMPLES)")
    print("=" * 85)

    for idx, sample_path in enumerate(sample_files, start=1):
        candidate_id = f"CAND-{idx:03d}"
        logger.info(f"Processing sample {idx}/{len(sample_files)}: {sample_path.name} -> {candidate_id}")
        
        with open(sample_path, "r", encoding="utf-8") as f:
            cv_text = f.read()

        start_time = time.time()
        try:
            extraction: CandidateExtraction = await agent.extract_candidate(cv_text=cv_text, candidate_id=candidate_id)
            elapsed = time.time() - start_time

            # Export to JSON artifact
            output_file = EXTRACTED_DIR / f"{candidate_id}_{sample_path.stem}.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as out:
                out.write(extraction.model_dump_json(indent=2))
                out.flush()
            logger.info(f"Saved extracted JSON artifact to: {output_file}")

            results.append({
                "candidate_id": candidate_id,
                "file_name": sample_path.name,
                "full_name": extraction.full_name or "N/A",
                "skills_count": len(extraction.skills),
                "years_exp": extraction.years_experience,
                "evidence_count": len(extraction.evidence),
                "missing_info_count": len(extraction.missing_information),
                "latency_sec": round(elapsed, 2),
                "status": "PASSED",
                "output_file": str(output_file)
            })

            logger.info(f"Successfully processed {candidate_id} in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to process {candidate_id} ({sample_path.name}): {e}", exc_info=True)
            results.append({
                "candidate_id": candidate_id,
                "file_name": sample_path.name,
                "full_name": "FAILED",
                "skills_count": 0,
                "years_exp": None,
                "evidence_count": 0,
                "missing_info_count": 0,
                "latency_sec": round(elapsed, 2),
                "status": f"FAILED: {e}",
                "output_file": "N/A"
            })

    # Summary Display
    print("\n" + "-" * 105)
    print(f"{'ID':<10} | {'File Name':<25} | {'Candidate Name':<20} | {'Exp (Yrs)':<10} | {'Skills':<8} | {'Evidence':<8} | {'Missing':<8} | {'Latency':<8} | {'Status'}")
    print("-" * 105)
    
    total_latency = 0
    passed_count = 0

    for r in results:
        exp_str = f"{r['years_exp']:.1f}" if r['years_exp'] is not None else "N/A"
        print(f"{r['candidate_id']:<10} | {r['file_name']:<25} | {r['full_name']:<20} | {exp_str:<10} | {r['skills_count']:<8} | {r['evidence_count']:<8} | {r['missing_info_count']:<8} | {r['latency_sec']:<8}s | {r['status']}")
        total_latency += r['latency_sec']
        if r['status'] == "PASSED":
            passed_count += 1

    print("-" * 105)
    avg_latency = total_latency / len(results) if results else 0
    print(f"SUMMARY: {passed_count}/{len(results)} Passed | Total Time: {total_latency:.2f}s | Avg Latency: {avg_latency:.2f}s/CV")
    print("=" * 105 + "\n")

    return passed_count == len(results)

if __name__ == "__main__":
    success = asyncio.run(run_phase1_tests())
    if not success:
        sys.exit(1)
