import asyncio
from openevolve import OpenEvolve

async def main():
    # Initialize the system
    evolve = OpenEvolve(
        initial_program_path="pack.py",
        evaluation_file="pack_evaluator.py",
        config_path="pack_evolution_config.yaml"
    )

    # Run the evolution
    best_program = await evolve.run(iterations=1000)
    print(f"Best program metrics:")
    for name, value in best_program.metrics.items():
        print(f"  {name}: {value:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
