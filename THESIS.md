# QiCompute Thesis

## Core Claim

Qi is mined. QiCompute moves Qi.

Qi creates currency through mining. QiCompute allocates currency through useful compute markets. Agents and humans participate in the same economic layer.

## Why Mining Matters

Mining is the only issuance mechanism. It gives idle authorized hardware a baseline economic role without requiring QiCompute to mint, stake, slash, or issue a second asset.

## Why Energy Is the Common Unit

Qi is reflective of energy, and so is inference. Mining converts joules into Qi at an observable rate, and every inference receipt records the joules the job consumed. That shared unit lets the marketplace anchor inference prices to the energy price of Qi: a joule spent serving a job should settle at least as much Qi as the same joule would have minted through mining. See `ENERGY_MODEL.md` for the implemented model.

## Why Stability Matters

A proof-of-useful-work market needs a unit of account, and a volatile token cannot be one: customers cannot budget, workers cannot compare inference against mining, and agents cannot hold working balances without speculation risk. QiCompute therefore quotes work in joules, which token volatility cannot touch, and converts to Qi at settlement through a smoothed parity oracle whose per-epoch movement is clamped, with spot premiums bounded in a corridor above the energy floor. Qi behaves like an energy-backed settlement medium for useful work, not a speculative asset; price discovery acts on the energy premium, not the currency.

Energy pricing must also not become cost-plus. Jobs are billed at a per-model benchmark joules-per-token rather than a worker's measured draw, so the price depends on the work, not on how wastefully a rig produced it. Beating the benchmark is the operator's efficiency margin, and the benchmark drifts toward fleet efficiency over time so hardware gains eventually reach customers.

## Why Inference Demand Matters

Inference demand is what turns idle hardware into useful market capacity. A worker should serve inference when verified job revenue beats the mining fallback floor.

## Why Privacy Matters

Privacy-sensitive customers need reasons to avoid centralized APIs or generic GPU clouds. QiCompute can model local routing, region preference, private payload handling, and verification without adding public networking to the prototype.

## Why Agents Matter

Agents can be customers, workers, verifiers, routers, or operators. They can mine Qi when they control authorized GPU hardware, earn existing Qi by providing useful verified services, and spend Qi on work they need.

## Why Mining Fallback Matters

Mining fallback gives compute operators a reservation price. If inference pays less than mining after energy and operating costs, rational workers mine or idle instead of serving jobs.

## Why Useful Work Should Not Mint Qi

Useful work should move existing Qi from customers to workers, verifiers, routers, and operators. Minting Qi for useful work would create a second issuance path and blur the settlement asset with marketplace rewards.

## Autonomous Compute Economy

The prototype now models customer choice, dynamic pricing, agent competition, reputation dynamics, regional markets, agent-to-agent trade, and monetary circulation. These are local deterministic simulations, not production market infrastructure.

## Current Evidence

Supported claims:

- QiCompute can model local escrow, settlement, refunds, worker payable accounting, and treasury accounting in deterministic tests.
- QiCompute can run local simulations for agent behavior, mining fallback, customer choice, pricing, reputation, regional markets, and monetary circulation.
- The prototype can avoid persisting raw prompts and raw outputs in its tested local paths.

Unsupported claims:

- Customers will pay for privacy, verification, local execution, or regional routing.
- Inference revenue will beat mining revenue on real hardware at realistic utilization.
- Agents will create enough demand or supply to sustain an autonomous compute economy.
- Qi will circulate rather than be hoarded.

Unknowns:

- Real verification overhead on actual hardware and realistic workloads.
- Real mining profitability under authorized Qi mining assumptions.
- Real customer willingness to pay.
- Real operator setup friction and uptime.
- Whether reputation and committees remain useful under adversarial public participation.

## Open Questions

- Will enough customers pay a premium for privacy, verification, or regional routing?
- How high must inference demand be before it reliably beats mining fallback?
- Which agent treasury policies survive long low-demand periods?
- Does reputation converge without unfairly excluding recoverable workers?
- Does mined Qi circulate through useful work or concentrate in idle treasuries?

## Current Prototype Limitations

The current system is an MVP simulation. It does not include blockchain integration, wallets, smart contracts, public networking, staking, governance tokens, production consensus, or real economic settlement. The models are deterministic and local-first so the assumptions are inspectable and testable.
