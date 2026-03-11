// BMW Car Catalog Data and Application Logic

const BMW_CARS = [
  {
    id: 1,
    model: "BMW 1 Series",
    series: "1 Series",
    bodyStyle: "Hatchback",
    year: 2024,
    specs: {
      engine: "1.5L 3-cyl Turbo",
      power: "136 hp",
      transmission: "7-speed DCT",
      drive: "FWD",
    },
  },
  {
    id: 2,
    model: "BMW 2 Series Coupé",
    series: "2 Series",
    bodyStyle: "Coupé",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD",
    },
  },
  {
    id: 3,
    model: "BMW 3 Series Sedan",
    series: "3 Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 4,
    model: "BMW 3 Series Touring",
    series: "3 Series",
    bodyStyle: "Estate",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 5,
    model: "BMW 4 Series Coupé",
    series: "4 Series",
    bodyStyle: "Coupé",
    year: 2024,
    specs: {
      engine: "3.0L 6-cyl Turbo",
      power: "382 hp",
      transmission: "8-speed Automatic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 6,
    model: "BMW 4 Series Convertible",
    series: "4 Series",
    bodyStyle: "Convertible",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD",
    },
  },
  {
    id: 7,
    model: "BMW 4 Series Gran Coupé",
    series: "4 Series",
    bodyStyle: "Fastback",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 8,
    model: "BMW 5 Series Sedan",
    series: "5 Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "255 hp",
      transmission: "8-speed Automatic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 9,
    model: "BMW 5 Series Touring",
    series: "5 Series",
    bodyStyle: "Estate",
    year: 2024,
    specs: {
      engine: "3.0L 6-cyl Turbo",
      power: "375 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 10,
    model: "BMW 7 Series",
    series: "7 Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "3.0L 6-cyl Turbo",
      power: "375 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 11,
    model: "BMW 8 Series Coupé",
    series: "8 Series",
    bodyStyle: "Coupé",
    year: 2024,
    specs: {
      engine: "4.4L V8 Turbo",
      power: "530 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 12,
    model: "BMW X1",
    series: "X Series",
    bodyStyle: "SUV",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "241 hp",
      transmission: "7-speed DCT",
      drive: "AWD",
    },
  },
  {
    id: 13,
    model: "BMW X3",
    series: "X Series",
    bodyStyle: "SUV",
    year: 2024,
    specs: {
      engine: "2.0L 4-cyl Turbo",
      power: "248 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 14,
    model: "BMW X5",
    series: "X Series",
    bodyStyle: "SUV",
    year: 2024,
    specs: {
      engine: "3.0L 6-cyl Turbo",
      power: "375 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 15,
    model: "BMW X7",
    series: "X Series",
    bodyStyle: "SUV",
    year: 2024,
    specs: {
      engine: "4.4L V8 Turbo",
      power: "523 hp",
      transmission: "8-speed Automatic",
      drive: "AWD",
    },
  },
  {
    id: 16,
    model: "BMW M3 Competition",
    series: "M Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "3.0L S58 Twin-Turbo",
      power: "503 hp",
      transmission: "8-speed M Steptronic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 17,
    model: "BMW M4 Coupé",
    series: "M Series",
    bodyStyle: "Coupé",
    year: 2024,
    specs: {
      engine: "3.0L S58 Twin-Turbo",
      power: "503 hp",
      transmission: "8-speed M Steptronic",
      drive: "RWD / AWD",
    },
  },
  {
    id: 18,
    model: "BMW M5",
    series: "M Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "4.4L V8 Turbo + Electric",
      power: "717 hp",
      transmission: "8-speed M Steptronic",
      drive: "AWD",
    },
  },
  {
    id: 19,
    model: "BMW Z4 Roadster",
    series: "Z Series",
    bodyStyle: "Roadster",
    year: 2024,
    specs: {
      engine: "3.0L 6-cyl Turbo",
      power: "382 hp",
      transmission: "8-speed Automatic",
      drive: "RWD",
    },
  },
  {
    id: 20,
    model: "BMW iX",
    series: "i Series",
    bodyStyle: "SUV",
    year: 2024,
    specs: {
      engine: "Dual Electric Motor",
      power: "516 hp",
      transmission: "Single-speed",
      drive: "AWD",
    },
  },
  {
    id: 21,
    model: "BMW i4",
    series: "i Series",
    bodyStyle: "Fastback",
    year: 2024,
    specs: {
      engine: "Dual Electric Motor",
      power: "536 hp",
      transmission: "Single-speed",
      drive: "AWD",
    },
  },
  {
    id: 22,
    model: "BMW i7",
    series: "i Series",
    bodyStyle: "Sedan",
    year: 2024,
    specs: {
      engine: "Dual Electric Motor",
      power: "536 hp",
      transmission: "Single-speed",
      drive: "AWD",
    },
  },
];

// Derive unique filter options from the data
function getUniqueValues(cars, key) {
  return [...new Set(cars.map((c) => c[key]))].sort();
}

function buildFilterOptions(selectEl, values, allLabel) {
  selectEl.innerHTML = `<option value="">${allLabel}</option>`;
  values.forEach((val) => {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = val;
    selectEl.appendChild(opt);
  });
}

function createCarCard(car) {
  const card = document.createElement("div");
  card.className = "car-card";
  card.setAttribute("role", "article");
  card.setAttribute("aria-label", car.model);

  card.innerHTML = `
    <div class="car-card-header">
      <div>
        <h2>${car.model}</h2>
        <div class="year">${car.year}</div>
      </div>
      <span class="car-series-badge">${car.series}</span>
    </div>
    <div class="car-card-body">
      <span class="car-body-style">${car.bodyStyle}</span>
      <ul class="car-specs">
        <li><span class="spec-label">Engine</span><span>${car.specs.engine}</span></li>
        <li><span class="spec-label">Power</span><span>${car.specs.power}</span></li>
        <li><span class="spec-label">Transmission</span><span>${car.specs.transmission}</span></li>
        <li><span class="spec-label">Drive</span><span>${car.specs.drive}</span></li>
      </ul>
    </div>
  `;

  return card;
}

function renderCars(cars) {
  const grid = document.getElementById("cars-grid");
  grid.innerHTML = "";

  if (cars.length === 0) {
    const empty = document.createElement("p");
    empty.className = "no-results";
    empty.textContent = "No models match your filters. Try adjusting the criteria.";
    grid.appendChild(empty);
  } else {
    cars.forEach((car) => grid.appendChild(createCarCard(car)));
  }

  document.getElementById("results-count").textContent =
    `Showing ${cars.length} model${cars.length !== 1 ? "s" : ""}`;
}

function applyFilters() {
  const series = document.getElementById("filter-series").value;
  const bodyStyle = document.getElementById("filter-body").value;
  const year = document.getElementById("filter-year").value;

  const filtered = BMW_CARS.filter((car) => {
    return (
      (!series || car.series === series) &&
      (!bodyStyle || car.bodyStyle === bodyStyle) &&
      (!year || String(car.year) === year)
    );
  });

  renderCars(filtered);
}

function init() {
  const seriesSelect = document.getElementById("filter-series");
  const bodySelect = document.getElementById("filter-body");
  const yearSelect = document.getElementById("filter-year");

  buildFilterOptions(seriesSelect, getUniqueValues(BMW_CARS, "series"), "All Series");
  buildFilterOptions(bodySelect, getUniqueValues(BMW_CARS, "bodyStyle"), "All Body Styles");
  buildFilterOptions(yearSelect, getUniqueValues(BMW_CARS, "year"), "All Years");

  seriesSelect.addEventListener("change", applyFilters);
  bodySelect.addEventListener("change", applyFilters);
  yearSelect.addEventListener("change", applyFilters);

  renderCars(BMW_CARS);
}

document.addEventListener("DOMContentLoaded", init);
