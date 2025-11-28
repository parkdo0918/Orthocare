# OrthoCare 핵심 논문 목록 (14개)

## 📚 저장 위치: `/data/papers/original/`

### OA (골관절염) 관련 논문
1. **Heidari 2011** - Knee osteoarthritis prevalence, risk factors
   - 파일명: `2011_heidari_knee_osteoarthritis.pdf`
   - 카테고리: `/data/papers/original/oa/`
   - 핵심: Age as major risk factor (OR 2.7)

2. **Zhang 2010** - OARSI recommendations for knee OA management
   - 파일명: `2010_zhang_oarsi_recommendations.pdf`
   - 카테고리: `/data/papers/original/oa/`
   - 핵심: Evidence-based treatment guidelines

3. **Reijman 2007** - BMI and knee OA relationship
   - 파일명: `2007_reijman_bmi_knee_oa.pdf`
   - 카테고리: `/data/papers/original/oa/`
   - 핵심: BMI >27 증가 위험 (OR 2.4)

### OVR (과사용) 관련 논문
4. **Crossley 2016** - Patellofemoral pain consensus statement
   - 파일명: `2016_crossley_patellofemoral_pain.pdf`
   - 카테고리: `/data/papers/original/ovr/`
   - 핵심: Anterior knee pain diagnosis criteria

5. **Taunton 2002** - Running injuries retrospective study
   - 파일명: `2002_taunton_running_injuries.pdf`
   - 카테고리: `/data/papers/original/ovr/`
   - 핵심: Activity increase as risk factor (LR+ 3.2)

6. **Fairbank 1984** - ITB friction syndrome
   - 파일명: `1984_fairbank_itb_syndrome.pdf`
   - 카테고리: `/data/papers/original/ovr/`
   - 핵심: Lateral knee pain in runners

### TRM (외상) 관련 논문
7. **Snoeker 2015** - Clinical prediction rule for meniscal tears
   - 파일명: `2015_snoeker_meniscal_tears.pdf`
   - 카테고리: `/data/papers/original/trm/`
   - 핵심: Locking/catching high LR+ (4.3-4.7)

8. **Benjaminse 2006** - ACL injury prevention programs
   - 파일명: `2006_benjaminse_acl_prevention.pdf`
   - 카테고리: `/data/papers/original/trm/`
   - 핵심: Neuromuscular training effectiveness

9. **Abram 2020** - Arthroscopic meniscectomy outcomes
   - 파일명: `2020_abram_meniscectomy_outcomes.pdf`
   - 카테고리: `/data/papers/original/trm/`
   - 핵심: Surgery vs conservative treatment

### INF (염증) 관련 논문
10. **Aletaha 2010** - Rheumatoid arthritis classification criteria
    - 파일명: `2010_aletaha_ra_criteria.pdf`
    - 카테고리: `/data/papers/original/inf/`
    - 핵심: Morning stiffness >30min diagnostic

11. **Hill 2001** - Knee effusion and synovitis assessment
    - 파일명: `2001_hill_knee_effusion.pdf`
    - 카테고리: `/data/papers/original/inf/`
    - 핵심: Swelling as inflammatory marker

12. **Altman 1991** - Classification of knee osteoarthritis
    - 파일명: `1991_altman_oa_classification.pdf`
    - 카테고리: `/data/papers/original/inf/`
    - 핵심: Clinical vs radiographic criteria

### 운동/재활 관련 논문
13. **Fransen 2015** - Exercise for knee OA Cochrane review
    - 파일명: `2015_fransen_exercise_cochrane.pdf`
    - 카테고리: `/data/papers/original/oa/`
    - 핵심: Exercise effectiveness (SMD -0.49 pain)

14. **Collins 2018** - Knee injury rehabilitation consensus
    - 파일명: `2018_collins_knee_rehabilitation.pdf`
    - 카테고리: `/data/papers/original/trm/`
    - 핵심: Progressive loading principles

## 📋 추가 필요 논문 (우선순위)

### High Priority
- [ ] WOMAC validation studies
- [ ] KOOS development paper
- [ ] Manual therapy effectiveness
- [ ] Injection therapy guidelines
- [ ] Weight loss impact on knee OA

### Medium Priority
- [ ] Gait analysis in knee disorders
- [ ] Imaging correlation with symptoms
- [ ] Post-surgical rehabilitation protocols
- [ ] Pediatric knee conditions
- [ ] Biomechanics of knee loading

### Low Priority
- [ ] Alternative medicine approaches
- [ ] Nutritional supplements
- [ ] Psychological factors in chronic pain
- [ ] Long-term prognosis studies

## 🔍 논문 입수 방법

1. **PubMed Central** (무료)
   - https://www.ncbi.nlm.nih.gov/pmc/

2. **Google Scholar**
   - PDF 링크 찾기

3. **ResearchGate**
   - 저자 직접 요청 가능

4. **Sci-Hub** (주의: 저작권)
   - 학술 목적으로만 사용

5. **대학 도서관 접속**
   - VPN 통한 접근

## 💾 저장 프로세스

```python
from data.manager import DataManager

dm = DataManager()

# 논문 추가
dm.add_paper(
    file_path="downloads/2011_heidari.pdf",
    category="oa",
    metadata={
        "year": 2011,
        "first_author": "heidari",
        "keyword": "knee_osteoarthritis",
        "evidence_level": "Level II",
        "key_findings": ["Age OR 2.7", "Female OR 1.5"]
    }
)
```

