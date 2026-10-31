#!/bin/zsh
# SocialForce calibration grid: 18 settings on the training runs of all three Jülich tests.
# Prints one line per setting as it finishes ("[k/18] ..."). Results: out/validation/sfgrid_*/summary.json
# Rank them afterwards with: .venv/bin/python scripts/score_validation.py "out/validation/sfgrid_*"
cd "$(dirname "$0")"
RUNS=(b090 b120 b160 b200 b250
      uo-080-240-240 uo-145-240-240 uo-240-240-240 uo-300-300-300 uo-180-180-095 uo-240-240-130 uo-300-300-120
      bot-360-160-160 bot-360-120-120 bot-360-200-200 bot-300-085-085 bot-360-050-050 bot-360-090-090
      bot-300-065-065 boa-300-050-070 boa-300-080-120)
k=0
for BF in 6000:12000 12000:24000 24000:48000; do
  for A in 1000 2000 4000; do
    for R in 0.2 0.25; do
      k=$((k + 1)); B=${BF%%:*}; F=${BF##*:}
      echo "[$k/18] $(date +%H:%M) start body_force=$B agent_scale=$A radius=$R"
      ../.venv/bin/python validate_juelich.py --model social_force --dataset all --seeds 2 \
        --name sfgrid_B${B}_A${A}_r${R} --runs $RUNS \
        --set agents.desired_speed_mps.mean=1.34 agents.desired_speed_mps.sd=0.26 \
              model_variants.social_force.model.body_force=$B model_variants.social_force.model.friction=$F \
              model_variants.social_force.agent.agent_scale=$A model_variants.social_force.agent.radius=$R \
        2>&1 | grep -E "^(bottleneck|corridor|bidirectional):|Error" | sed "s/^/      /"
    done
  done
done
echo "$(date +%H:%M) all 18 done"
