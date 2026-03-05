package sa.gov.pension.business.command;

import sa.gov.pension.business.service.BeneficiaryService;

public class BenificiaryRemove {

    private BeneficiaryService beneficiaryService;

    public void execute(String beneficiaryId) throws Exception {
        validateInput(beneficiaryId);
        beneficiaryService.removeBeneficiary(beneficiaryId);
        logAction("Removed beneficiary: " + beneficiaryId);
    }

    private void validateInput(String id) {
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("Beneficiary ID cannot be null or empty");
        }
    }

    private void logAction(String message) {
        System.out.println("[AUDIT] " + message);
    }
}
