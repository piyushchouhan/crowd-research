#!/bin/zsh
# AnticipationVelocity calibration on the training runs of the Jülich tests, in two stages:
#   ./avm_grid.sh 1               time gap x radius on the bottleneck (as for CollisionFreeSpeed)
#   ./avm_grid.sh 2 <T> <r>       anticipation x reaction time on all three tests, two-way by replay
# Results: out/validation/avm1_* and avm2_*; rank with
#   .venv/bin/python scripts/score_validation.py "out/validation/avm2_*"
cd "$(dirname "$0")"
BOTTLENECK=(b090 b120 b160 b200 b250)
RUNS=($BOTTLENECK
      uo-080-240-240 uo-145-240-240 uo-240-240-240 uo-300-300-300 uo-180-180-095 uo-240-240-130 uo-300-300-120
      bot-360-160-160 bot-360-120-120 bot-360-200-200 bot-300-085-085 bot-360-050-050 bot-360-090-090
      bot-300-065-065 boa-300-050-070 boa-300-080-120)
A=model_variants.anticipation_velocity.agent
SPEED=(agents.desired_speed_mps.mean=1.34 agents.desired_speed_mps.sd=0.26)
run() {  # name, dataset, runs..., -- overrides...
  local name=$1 dataset=$2; shift 2
  local runs=(${@[1,$(( ${@[(i)--]} - 1 ))]}) sets=(${@[$(( ${@[(i)--]} + 1 )),-1]})
  echo "$(date +%H:%M) $name"
  ../.venv/bin/python validate_juelich.py --model anticipation_velocity --dataset $dataset --seeds 2 --replay \
    --name $name --runs $runs --set $SPEED $sets 2>&1 | grep -E "^(bottleneck|corridor|bidirectional):|Error" \
    | sed "s/^/      /"
}
if [[ $1 == 1 ]]; then
  for T in 0.4 0.5 0.6 0.7; do
    for R in 0.15 0.175; do
      run avm1_T${T}_r${R} bottleneck $BOTTLENECK -- $A.time_gap=$T $A.radius=$R
    done
  done
elif [[ $1 == 2 ]]; then
  for AT in 0.5 1.0 2.0; do
    for RT in 0.1 0.3 0.6; do
      run avm2_T$2_r$3_a${AT}_rt${RT} all $RUNS -- $A.time_gap=$2 $A.radius=$3 \
        $A.anticipation_time=$AT $A.reaction_time=$RT
    done
  done
fi
echo "$(date +%H:%M) done"
