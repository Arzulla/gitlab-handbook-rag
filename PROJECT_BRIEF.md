# Project Brief: Permission-Aware RAG over the GitLab Handbook

> A permission-aware RAG assistant over GitLab's public handbook. The same question
> returns different answers depending on the user's role, and restricted content never
> leaks — verified by a dedicated security eval suite.

**Məqsəd:** Qlobal AI Engineer interview-ları üçün portfolio layihəsi.
**Vaxt büdcəsi:** ~25-30 saat. **Dil:** Python. **Repo dili:** ingiliscə.

---

## Niyə bu layihə (05.10.2026 komanda müzakirəsinin nəticəsi)

- **Real data:** GitLab Handbook real şirkətin 2000+ səhifəlik daxili sənədləridir, süni data deyil.
- **Real biznes problemi:** Enterprise RAG-da əsas risk icazələrdir ("adi işçi direktorun maaşını görür").
- **Qlobal auditoriya üçün aydın:** ingiliscə, hamının tanıdığı şirkət.
- **Fərqləndirici:** iki növ eval: keyfiyyət + təhlükəsizlik (leak rate), ablation cədvəli ilə.
- **Rədd edilən ideyalar:** Azərbaycan Əmək Məcəlləsi (qlobal interviewer oxuya bilmir; 2-ci layihə ola bilər), Spring docs assistenti (çox adi, artıq mövcuddur).

---

## Scope

### ✅ Daxildir
1. Handbook-un 5-6 departament bölməsi (bütün handbook yox), hər chunk-da mənbə URL-i
2. Rol → departament icazə modeli (chunk metadata-sında)
3. Hybrid search (vector + BM25) + cross-encoder rerank
4. **İcazə filtri retrieval mərhələsində** (vector DB `where` filtri), prompt-da yox
5. Query rewriting (orijinal + yenidən yazılmış sual, orijinal suala görə rerank)
6. Mənbə göstərən cavablar; kontekstdə yoxdursa "bilmirəm"
7. Eval: keyfiyyət + təhlükəsizlik + latency/cost; ablation cədvəli
8. Sadə UI (Gradio) rol seçimi ilə; Docker; mümkünsə canlı demo
9. README: dizayn qərarları, nəticələr, "nə işləmədi" bölməsi

### ❌ Daxil deyil
Agentic RAG, graph DB, fine-tuning, real authentication, mikroservislər, React frontend.

---

## Arxitektura (ilkin)

```
INGEST:  handbook markdown → başlıqlara görə chunk → metadata (section, allowed_roles, url)
         → embedding → Chroma  +  BM25 index

QUERY:   (question, role)
         → rewrite query
         → vector search + BM25, HƏR İKİSİ role filtri ilə
         → birləşdir (RRF) + təkrarları at
         → cross-encoder rerank (orijinal suala görə) → top-k
         → LLM cavab (mənbələrlə)
```

## Rol modeli (qaralama, Mərhələ 1-də dəqiqləşəcək)

| Rol | Görə bildiyi bölmələr |
|---|---|
| employee | Company, Engineering (ümumi) |
| people_ops | + People Group |
| finance | + Finance |
| legal | + Legal & Corporate Affairs |

README-də dürüst qeyd: *data realdır, icazə modeli handbook-un departament strukturu əsasında simulyasiya edilib.*

---

## Eval planı

**Golden set** (`eval/golden_set.jsonl`), hər sətir:
`{id, question, role, expected_answer, relevant_sources, category}`
Kateqoriyalar: `factual`, `follow_up`, `exact_term`, `restricted` (icazəsiz giriş), `injection`.

| Növ | Metriklər |
|---|---|
| Retrieval keyfiyyəti | MRR, Recall@k, Precision@k |
| Cavab keyfiyyəti | LLM judge (accuracy, completeness, relevance), judge modeli SABİT |
| Təhlükəsizlik | Leak rate (hədəf 0%), injection müqaviməti |
| Əməliyyat | p50/p95 latency, sorğu başına cost |

**Qaydalar:** hər dəfə bir dəyişiklik; hər eksperimenti `eval/results/`-ə yaz; eval-ı ən az 2 dəfə işə sal (LLM qeyri-deterministikdir).

---

## Mərhələlər

- [ ] **1. Data + rol modeli:** lisenziyanı yoxla, bölmələri seç, parse/chunk, metadata, testlər (~5 saat)
- [ ] **2. Baseline:** yalnız vector search + role filtri + sadə UI (~4 saat)
- [ ] **3. Golden set + eval skripti:** 60-80 sual, baseline nəticələri (~6 saat)
- [ ] **4. Təkmilləşdirmələr:** hybrid → rerank → rewriting, hər biri ayrıca ölçülür (~6 saat)
- [ ] **5. Təhlükəsizlik eval-ı:** restricted + injection testləri, leak rate (~3 saat)
- [ ] **6. Təhvil:** README, ablation cədvəli, GIF demo, Docker, deploy (~4 saat)

---

## Riskler
- Handbook lisenziyasını başlamazdan əvvəl yoxla (2016-cı il blog yazısında CC BY-SA 4.0 qeyd olunub; hazırkı vəziyyəti təsdiqlə).
- Handbook çox böyükdür: kiçik başla.
- İcazə modelinin simulyasiya olduğunu gizlətmə.

---

## Qərarlar jurnalı (ADR)
Hər vacib qərar buraya qısa yazılır: **Qərar → Alternativlər → Niyə → Ölçülən nəticə.**
Bu bölmə interview-da "niyə belə etdiniz?" sualının cavabıdır.

<!-- Nümunə:
### ADR-001: Chunking başlıqlara görə, LLM ilə yox
- Alternativ: LLM semantic chunking
- Niyə: handbook artıq markdown başlıqları ilə strukturlaşdırılıb; deterministik, pulsuz
- Nəticə: (eval nəticəsi)
-->
