import math
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class Evaluator:
    @staticmethod
    def evaluate_extraction(ai_extractions: List[Dict[str, Any]], ground_truths: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates extraction precision, recall, F1, and accuracy against ground truths.
        """
        gt_map = {gt["candidate_id"]: gt for gt in ground_truths}
        
        total_skill_tp = 0
        total_skill_fp = 0
        total_skill_fn = 0
        exp_correct = 0
        exp_total = 0
        
        for ai_cand in ai_extractions:
            cid = ai_cand["candidate_id"]
            if cid not in gt_map:
                continue
            gt = gt_map[cid]
            
            ai_skills = set(s.lower() for s in ai_cand.get("skills", []))
            gt_skills = set(s.lower() for s in gt.get("skills", []))
            
            tp = len(ai_skills.intersection(gt_skills))
            fp = len(ai_skills.difference(gt_skills))
            fn = len(gt_skills.difference(ai_skills))
            
            total_skill_tp += tp
            total_skill_fp += fp
            total_skill_fn += fn
            
            # Experience accuracy
            ai_exp = ai_cand.get("years_experience")
            gt_exp = gt.get("years_experience")
            if gt_exp is not None:
                exp_total += 1
                if ai_exp is not None and abs(float(ai_exp) - float(gt_exp)) <= 0.5:
                    exp_correct += 1
                    
        precision = total_skill_tp / (total_skill_tp + total_skill_fp) if (total_skill_tp + total_skill_fp) > 0 else 0.0
        recall = total_skill_tp / (total_skill_tp + total_skill_fn) if (total_skill_tp + total_skill_fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        exp_accuracy = (exp_correct / exp_total) if exp_total > 0 else 0.0
        
        return {
            "skill_precision": round(precision, 4),
            "skill_recall": round(recall, 4),
            "skill_f1": round(f1, 4),
            "experience_accuracy": round(exp_accuracy, 4),
            "total_candidates_evaluated": len(gt_map)
        }

    @staticmethod
    def evaluate_matching(ai_matches: List[Dict[str, Any]], ground_truth_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates classification metrics (Accuracy, Precision, Recall, F1, FPR, FNR) and Ranking metrics (NDCG@10, MRR, P@5).
        """
        gt_map = {(m["candidate_id"], m["job_id"]): m["label"] for m in ground_truth_matches}
        
        tp = fp = tn = fn = 0
        
        for ai in ai_matches:
            key = (ai["candidate_id"], ai["job_id"])
            if key not in gt_map:
                continue
                
            gt_label = gt_map[key]
            ai_label = ai["recommendation"]
            
            is_gt_positive = gt_label == "SHORTLIST"
            is_ai_positive = ai_label == "SHORTLIST"
            
            if is_gt_positive and is_ai_positive:
                tp += 1
            elif not is_gt_positive and is_ai_positive:
                fp += 1
            elif is_gt_positive and not is_ai_positive:
                fn += 1
            else:
                tn += 1
                
        total = tp + fp + tn + fn
        accuracy = (tp + tn) / total if total > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        
        # Ranking Metrics: Precision@5, NDCG@10, MRR per Job
        jobs_ai = {}
        for ai in ai_matches:
            jobs_ai.setdefault(ai["job_id"], []).append(ai)
            
        ndcg_scores = []
        mrr_scores = []
        p5_scores = []
        
        for job_id, items in jobs_ai.items():
            # Rank candidates by total score descending
            ranked = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
            
            # P@5
            top5 = ranked[:5]
            top5_hits = sum(1 for item in top5 if gt_map.get((item["candidate_id"], job_id)) == "SHORTLIST")
            p5_scores.append(top5_hits / min(5, len(top5)) if top5 else 0.0)
            
            # MRR
            first_hit_rank = 0
            for rank_idx, item in enumerate(ranked, start=1):
                if gt_map.get((item["candidate_id"], job_id)) == "SHORTLIST":
                    first_hit_rank = rank_idx
                    break
            mrr_scores.append(1.0 / first_hit_rank if first_hit_rank > 0 else 0.0)
            
            # NDCG@10
            top10 = ranked[:10]
            dcg = 0.0
            idcg = 0.0
            
            for i, item in enumerate(top10):
                rel = 1.0 if gt_map.get((item["candidate_id"], job_id)) == "SHORTLIST" else 0.0
                dcg += rel / math.log2(i + 2)
                
            # Ideal DCG
            num_relevant = sum(1 for item in ranked if gt_map.get((item["candidate_id"], job_id)) == "SHORTLIST")
            for i in range(min(10, num_relevant)):
                idcg += 1.0 / math.log2(i + 2)
                
            ndcg_scores.append(dcg / idcg if idcg > 0 else 1.0)

        return {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
            "precision_at_5": round(sum(p5_scores) / len(p5_scores), 4) if p5_scores else 0.0,
            "ndcg_at_10": round(sum(ndcg_scores) / len(ndcg_scores), 4) if ndcg_scores else 0.0,
            "mrr": round(sum(mrr_scores) / len(mrr_scores), 4) if mrr_scores else 0.0,
            "total_matches_evaluated": total
        }
