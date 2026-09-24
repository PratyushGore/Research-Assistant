import { BrowserRouter, Routes, Route } from "react-router-dom";

import Home from "./pages/Home";
import ResearchSetup from "./pages/ResearchSetup";
import GuidedInput from "./pages/GuidedInput";
import ResearchProgress from "./pages/ResearchProgress";
import Outputs from "./pages/Outputs";

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route
          path="/"
          element={<Home />}
        />

        <Route
          path="/research"
          element={<ResearchSetup />}
        />

        <Route
          path="/guided-input"
          element={<GuidedInput />}
        />

        <Route
          path="/research-progress"
          element={<ResearchProgress />}
        />

        <Route
          path="/outputs"
          element={<Outputs />}
        />

      </Routes>
    </BrowserRouter>
  );
}

export default App;