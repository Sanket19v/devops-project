#!/usr/bin/env python3
"""AI Cloud Cost Optimizer: collect -> analyse -> recommend -> Terraform plan -> human approval -> apply.
  python optimizer.py --mock                (no AWS needed)
  python optimizer.py --region us-east-1    (real AWS, read-only calls)
  python optimizer.py --apply               (plan/apply with two confirmations)"""
import argparse, datetime as dt, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common.llm import ask

# Rough on-demand $/month (us-east-1, Linux). ESTIMATES - check the AWS pricing page.
PRICE = {"t3.nano": 3.8, "t3.micro": 7.6, "t3.small": 15.2, "t3.medium": 30.4,
         "t3.large": 60.8, "t3.xlarge": 121.6, "t3.2xlarge": 243.2}
SIZES = list(PRICE)
GP3_GB, SNAP_GB = 0.08, 0.05
TFVARS = os.path.join(HERE, "terraform", "optimized.tfvars.json")


def collect_aws(region):
    import boto3
    ec2, cw = boto3.client("ec2", region_name=region), boto3.client("cloudwatch", region_name=region)
    end = dt.datetime.now(dt.timezone.utc); start = end - dt.timedelta(days=14)
    data = {"instances": [], "volumes": [], "snapshots": []}

    def stat(iid, s):
        pts = cw.get_metric_statistics(Namespace="AWS/EC2", MetricName="CPUUtilization",
              Dimensions=[{"Name": "InstanceId", "Value": iid}], StartTime=start, EndTime=end,
              Period=3600, Statistics=[s])["Datapoints"]
        v = [p[s] for p in pts]
        if not v:
            return None
        return sum(v) / len(v) if s == "Average" else max(v)

    for r in ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])["Reservations"]:
        for i in r["Instances"]:
            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), i["InstanceId"])
            data["instances"].append({"id": i["InstanceId"], "name": name, "type": i["InstanceType"],
                                      "cpu_avg": stat(i["InstanceId"], "Average"), "cpu_max": stat(i["InstanceId"], "Maximum")})
    for v in ec2.describe_volumes(Filters=[{"Name": "status", "Values": ["available"]}])["Volumes"]:
        data["volumes"].append({"id": v["VolumeId"], "size_gb": v["Size"]})
    for s in ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]:
        age = (end - s["StartTime"]).days
        if age > 90:
            data["snapshots"].append({"id": s["SnapshotId"], "size_gb": s["VolumeSize"], "age_days": age})
    return data


def analyse(data):
    out = []
    for i in data["instances"]:
        if i["cpu_avg"] is None or i["type"] not in PRICE:
            continue
        if i["cpu_avg"] < 5 and i["cpu_max"] < 20:
            out.append({"kind": "idle_instance", "name": i["name"], "action": "stop/terminate",
                        "saving": PRICE[i["type"]], "why": f"avg CPU {i['cpu_avg']:.1f}%, max {i['cpu_max']:.0f}% over 14d"})
        elif i["cpu_avg"] < 20 and i["cpu_max"] < 60 and SIZES.index(i["type"]) > 0:
            new = SIZES[SIZES.index(i["type"]) - 1]
            out.append({"kind": "right_size", "name": i["name"], "action": f"{i['type']} -> {new}", "new_type": new,
                        "saving": PRICE[i["type"]] - PRICE[new], "why": f"avg CPU {i['cpu_avg']:.1f}%, max {i['cpu_max']:.0f}%"})
    for v in data["volumes"]:
        out.append({"kind": "unused_volume", "name": v["id"], "action": "snapshot then delete",
                    "saving": v["size_gb"] * GP3_GB, "why": f"{v['size_gb']} GB, not attached"})
    for s in data["snapshots"]:
        out.append({"kind": "old_snapshot", "name": s["id"], "action": "delete if not needed",
                    "saving": s["size_gb"] * SNAP_GB, "why": f"{s['age_days']} days old"})
    return sorted(out, key=lambda x: -x["saving"])


def write_tfvars(data, findings):
    idle = {f["name"] for f in findings if f["kind"] == "idle_instance"}
    resize = {f["name"]: f["new_type"] for f in findings if f["kind"] == "right_size"}
    inst = {i["name"]: {"type": resize.get(i["name"], i["type"])} for i in data["instances"] if i["name"] not in idle}
    with open(TFVARS, "w") as f:
        json.dump({"instances": inst}, f, indent=2)
    return TFVARS


def tf(*args):
    return subprocess.run(["terraform", f"-chdir={os.path.join(HERE, 'terraform')}", *args]).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true"); ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    data = json.load(open(os.path.join(HERE, "sample_data.json"))) if a.mock else collect_aws(a.region)
    findings = analyse(data)
    total = sum(f["saving"] for f in findings)
    print(f"\n{'KIND':<15}{'RESOURCE':<14}{'ACTION':<24}{'SAVE $/mo':>10}  WHY")
    for f in findings:
        print(f"{f['kind']:<15}{f['name']:<14}{f['action']:<24}{f['saving']:>10.2f}  {f['why']}")
    print(f"\nEstimated total savings: ${total:.2f}/month (estimates only)\n")

    brief = ask("You are a FinOps engineer. Prioritise these findings, flag risks (e.g. burstable CPU credits, "
                "snapshots needed for compliance) and say what to verify before acting. Max 150 words.",
                json.dumps(findings))
    if brief:
        print("AI notes:\n" + brief + "\n")

    path = write_tfvars(data, findings)
    print(f"Terraform vars written: {path}")
    if a.apply:
        if input("Run `terraform plan` with these changes? (yes/no): ").strip() != "yes":
            return
        tf("init"); tf("plan", f"-var-file={path}")
        if input("APPLY these changes to real infrastructure? Type 'yes': ").strip() == "yes":
            tf("apply", "-auto-approve", f"-var-file={path}")
        else:
            print("Aborted. Nothing changed.")


if __name__ == "__main__":
    main()
