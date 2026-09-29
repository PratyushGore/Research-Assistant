import { BrowserRouter, Routes, Route } from "react-router-dom";

import Home from "./pages/Home";
import ResearchSetup from "./pages/ResearchSetup";
import GuidedInput from "./pages/GuidedInput";
import ResearchProgress from "./pages/ResearchProgress";
import ResearchResults from "./pages/ResearchResults";
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
          path="/research-progress"
          element={<ResearchProgress />}
        />

        <Route
          path="/research-results"
          element={<ResearchResults />}
        />

        <Route
          path="/guided-input"
          element={<GuidedInput />}
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