console.log("Smart Parking JavaScript Started");

// ==========================
// LIVE SLOT STATUS (unchanged source: /parking-data, fed by Arduino)
// ==========================

async function updateParking() {
    try {
        const response = await fetch("/parking-data");
        const data = await response.json();

        updateSlot(1, data);
        updateSlot(2, data);

        let occupied = 0;
        if (data.slot1 === "OCCUPIED") occupied++;
        if (data.slot2 === "OCCUPIED") occupied++;

        document.getElementById("occupied").textContent = occupied;
        document.getElementById("available").textContent = 2 - occupied;

    } catch (error) {
        console.error("ERROR updating parking data:", error);
    }
}

function updateSlot(num, data) {
    const status = data[`slot${num}`];
    const entry = data[`entry_time_slot${num}`];
    const duration = data[`duration_slot${num}`];
    const cost = data[`cost_slot${num}`];
    const currency = data.currency || "₹";

    document.getElementById(`status${num}`).textContent = status;
    document.getElementById(`entry${num}`).textContent = entry || "--";
    document.getElementById(`duration${num}`).textContent = duration || "--";
    document.getElementById(`cost${num}`).textContent =
        `${currency}${(cost || 0).toFixed(2)}`;

    const slotEl = document.getElementById(`slot${num}`);
    slotEl.className = status === "OCCUPIED" ? "slot occupied" : "slot empty";
}

// ==========================
// DAILY OCCUPIED / FREE TIME + REVENUE
// ==========================

async function updateDailyStats() {
    try {
        const response = await fetch("/daily-stats");
        const data = await response.json();
        const currency = data.currency || "₹";

        document.getElementById("revenueToday").textContent =
            `${currency}${data.total_revenue_today.toFixed(2)}`;

        [1, 2].forEach((num) => {
            const s = data[`slot${num}`];
            if (!s) return;

            document.getElementById(`occupiedToday${num}`).textContent = s.occupied_formatted;
            document.getElementById(`freeToday${num}`).textContent = s.free_formatted;
            document.getElementById(`progress${num}`).style.width =
                `${Math.min(s.occupied_percent, 100)}%`;
        });

    } catch (error) {
        console.error("ERROR updating daily stats:", error);
    }
}

// ==========================
// MONTHLY SUMMARY
// ==========================

async function loadAvailableMonths() {
    try {
        const response = await fetch("/available-months");
        let months = await response.json();

        const currentMonth = new Date().toISOString().slice(0, 7);
        if (!months.includes(currentMonth)) {
            months = [currentMonth, ...months];
        }

        const picker = document.getElementById("monthPicker");
        picker.innerHTML = months
            .map((m) => `<option value="${m}">${m}</option>`)
            .join("");

        picker.value = currentMonth;
        picker.addEventListener("change", () => updateMonthlyStats(picker.value));

        updateMonthlyStats(currentMonth);

    } catch (error) {
        console.error("ERROR loading months:", error);
    }
}

async function updateMonthlyStats(month) {
    try {
        const response = await fetch(`/monthly-stats?month=${month}`);
        const data = await response.json();
        const currency = data.currency || "₹";

        document.getElementById("monthVehicles").textContent = data.total_vehicles;
        document.getElementById("monthRevenue").textContent =
            `${currency}${data.total_revenue.toFixed(2)}`;

        const s1 = data.slot_breakdown["Slot 1"] || { vehicles: 0, revenue: 0 };
        const s2 = data.slot_breakdown["Slot 2"] || { vehicles: 0, revenue: 0 };

        document.getElementById("monthSlot1").textContent =
            `${s1.vehicles} / ${currency}${s1.revenue.toFixed(2)}`;
        document.getElementById("monthSlot2").textContent =
            `${s2.vehicles} / ${currency}${s2.revenue.toFixed(2)}`;

    } catch (error) {
        console.error("ERROR updating monthly stats:", error);
    }
}

// ==========================
// PARKING HISTORY TABLE (with filters)
// ==========================

function buildHistoryQuery() {
    const params = new URLSearchParams();

    const slot = document.getElementById("filterSlot").value;
    const startDate = document.getElementById("filterStartDate").value;
    const endDate = document.getElementById("filterEndDate").value;
    const startTime = document.getElementById("filterStartTime").value;
    const endTime = document.getElementById("filterEndTime").value;
    const minCost = document.getElementById("filterMinCost").value;
    const maxCost = document.getElementById("filterMaxCost").value;

    if (slot) params.set("slot", slot);
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    if (startTime) params.set("start_time", startTime);
    if (endTime) params.set("end_time", endTime);
    if (minCost) params.set("min_cost", minCost);
    if (maxCost) params.set("max_cost", maxCost);

    return params.toString();
}

async function updateHistory() {
    try {
        const query = buildHistoryQuery();
        const url = query ? `/parking-history?${query}` : "/parking-history";

        const response = await fetch(url);
        const history = await response.json();

        const body = document.getElementById("historyBody");

        if (!history.length) {
            body.innerHTML = `<tr><td colspan="6" class="empty-row">No records match these filters</td></tr>`;
            return;
        }

        body.innerHTML = history
            .slice(0, 100)
            .map((h) => `
                <tr>
                    <td>${h.slot}</td>
                    <td>${h.date}</td>
                    <td>${h.entry_time}</td>
                    <td>${h.exit_time}</td>
                    <td>${h.duration}</td>
                    <td>₹${h.cost.toFixed(2)}</td>
                </tr>
            `)
            .join("");

    } catch (error) {
        console.error("ERROR updating history:", error);
    }
}

function setupFilterControls() {
    document.getElementById("applyFilters").addEventListener("click", updateHistory);

    document.getElementById("clearFilters").addEventListener("click", () => {
        document.getElementById("filterSlot").value = "";
        document.getElementById("filterStartDate").value = "";
        document.getElementById("filterEndDate").value = "";
        document.getElementById("filterStartTime").value = "";
        document.getElementById("filterEndTime").value = "";
        document.getElementById("filterMinCost").value = "";
        document.getElementById("filterMaxCost").value = "";
        updateHistory();
    });
}

// ==========================
// RUN
// ==========================

setupFilterControls();

updateParking();
updateDailyStats();
updateHistory();
loadAvailableMonths();

// Real-time slot status: every second (kept exactly as before)
setInterval(updateParking, 1000);

// Daily stats: every 5 seconds
setInterval(updateDailyStats, 5000);

// History and monthly stats refresh less often, and only if no filter is being actively typed
setInterval(updateHistory, 8000);